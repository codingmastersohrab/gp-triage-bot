"""
Adaptive dialogue engine for the triage chatbot.

The bot collects information in a fixed order: main issue, duration, severity,
then a set of pathway-specific yes/no questions. Once all questions are answered,
it computes a routing outcome and presents a summary for the patient to confirm.

Confirmation behaviour:
  - If the patient says "I meant X" or "actually X" for something already recorded,
    the correction is held in mid_correction and confirmed once before being applied.
  - If the patient says "yes" to a red-flag question, the answer is held in
    pending_red_flag_confirm and confirmed once before being written.
  - Both checks happen at the very top of handle_user_text and next_bot_message,
    before any phase logic, so they cannot be bypassed.

Processing order (both handle_user_text and next_bot_message follow this):
  1. mid_correction pending
  2. pending_red_flag_confirm
  3. preamble collection (main issue, duration, severity)
  4. pathway questions
  5. summary confirmation and optional correction
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from app.models import Duration, TriageChecksheet
from app.parsers import parse_duration, parse_severity_0_10
from app.pathways import (
    detect_category,
    get_pathway_name,
    get_pathway_steps,
    next_pathway_step,
    check_red_flags,
)
from app.routing import compute_route
from app.summary import generate_patient_summary, generate_completion_message


# Response helpers

def is_yes(text: str) -> bool:
    t = text.strip().lower()
    return t in {
        "yes", "y", "yeah", "yep", "yup", "correct", "right",
        "that's right", "thats right", "ok", "okay", "sure", "absolutely",
        "confirmed", "confirm", "true",
    }


def is_no(text: str) -> bool:
    t = text.strip().lower()
    return t in {
        "no", "n", "nope", "nah", "not really", "incorrect",
        "wrong", "false", "negative",
    }


# Correction detection

# Matches: "I meant 2 days", "actually 5", "sorry, 1 week", "correction: chest pain"
_CORRECTION_RE = re.compile(
    r'^(?:i meant|i mean|actually,?\s*|sorry,?\s*(?:i meant\s*)?|correction:?\s*)(.+)',
    re.IGNORECASE,
)


def _extract_correction(text: str) -> Optional[str]:
    """Return the corrected value fragment if text looks like a self-correction."""
    m = _CORRECTION_RE.match(text.strip())
    return m.group(1).strip() if m else None


def _last_answered_step_key(steps, pathway_answers: dict) -> Optional[str]:
    """Return the key of the most recently answered pathway step, or None."""
    last = None
    for step in steps:
        if step.key in pathway_answers:
            last = step.key
    return last


# State reader — decides what the bot should say next

def next_bot_message(session: TriageChecksheet) -> str:  # noqa: C901
    """
    Pure read of session state → next bot message string.
    Side effects: sets route_outcome / route_rationale / route_decided_at
    and summary_presented when those transitions first occur.
    (main.py calls store.update *after* this to persist those side-effects.)
    """

    # Priority 1: mid-correction awaiting confirmation.
    # Checked before anything else so a pending confirmation is always shown,
    # even if we're still mid-preamble (e.g. severity not yet collected).
    if session.mid_correction is not None:
        field = session.mid_correction["field"]
        value = session.mid_correction["value"]
        if field == "duration":
            # Coerce from plain dict if reloaded from DB JSON
            if isinstance(value, dict):
                value = Duration.model_validate(value)
            d = value
            return (
                f"Just to check \u2014 you meant {d.value} {d.unit.value}, "
                f"is that right? (yes/no)"
            )
        if field == "severity_0_10":
            return f"Just to check \u2014 you meant severity {value}/10, is that right? (yes/no)"
        if field == "pathway_answer":
            key = session.mid_correction["key"]
            new_val_str = "yes" if value else "no"
            step = _find_step(session, key)
            q = _strip_prompt(step.question) if step else key
            return (
                f"Just to check \u2014 you meant {new_val_str} to: "
                f"\u201c{q}\u201d. Is that correct? (yes/no)"
            )
        if field == "main_issue":
            return f"Just to check \u2014 you meant: \u201c{value}\u201d, is that right? (yes/no)"

    # Priority 2: red-flag answer awaiting confirmation
    if session.pending_red_flag_confirm is not None:
        key = session.pending_red_flag_confirm["key"]
        step = _find_step(session, key)
        if step:
            q = _strip_prompt(step.question)
            return (
                f"Just to confirm \u2014 {q}? "
                f"You said yes. Is that correct? (yes/no)"
            )
        return "Just to confirm your previous answer was yes. Is that correct? (yes/no)"

    # Phase 1: collect main issue
    if session.main_issue is None:
        return "What's the main issue you're calling about today? (One sentence is fine.)"

    # Phase 2: collect duration
    if session.duration is None:
        return "How long has this been going on? (e.g., '2 days', 'a week', '3 hours')"

    # Phase 3: collect severity
    if session.severity_0_10 is None:
        return "How severe is it right now on a scale of 0 to 10, where 10 is the worst you can imagine?"

    # Phase 4: pathway questions
    category = session.symptom_category or "other"
    steps    = get_pathway_steps(category)

    if session.route_outcome is None:
        early = check_red_flags(category, session.pathway_answers)
        if early is None:
            pending = next_pathway_step(steps, session.pathway_answers)
            if pending is not None:
                return pending.question

        outcome, rationale = compute_route(session)
        session.route_outcome    = outcome
        session.route_rationale  = rationale
        session.route_decided_at = datetime.now(timezone.utc)

    # Phase 5: present patient-facing summary
    if not session.summary_presented:
        session.summary_presented = True
        return generate_patient_summary(session)

    # Phase 6: await summary confirmation
    if session.summary_confirmed is None:
        return "Please reply yes or no \u2014 does the summary above look correct?"

    # Phase 7: correction
    if not session.summary_confirmed:
        if session.awaiting_correction_of is None:
            session.awaiting_correction_of = "asking"
            return (
                "No problem. Which part would you like to correct? "
                "Please say: issue, duration, or severity."
            )
        if session.awaiting_correction_of == "asking":
            return "Please tell me which part to correct: issue, duration, or severity."

    # Phase 8: done
    return generate_completion_message(session)


# State writer — processes user input and updates the session

def handle_user_text(session: TriageChecksheet, user_text: str) -> None:  # noqa: C901
    """
    Processes one user message and updates session state.
    Voice transcripts share this exact code path — no separate handling needed.
    """
    text = user_text.strip()
    session.number_of_turns += 1

    # Priority 1: handle mid-correction confirmation.
    # Must be checked before any collection phase so the confirmation loop
    # can't be skipped if the bot has already moved on to the next question.
    if session.mid_correction is not None:
        if is_yes(text):
            field = session.mid_correction["field"]
            value = session.mid_correction["value"]
            if field == "duration":
                # When loaded from the DB the Duration Pydantic model is
                # deserialised as a plain dict inside Dict[str, Any].  Coerce it
                # back before assigning so store.py can access .value / .unit.
                if isinstance(value, dict):
                    value = Duration.model_validate(value)
                session.duration = value
            elif field == "severity_0_10":
                session.severity_0_10 = value
            elif field == "pathway_answer":
                session.pathway_answers[session.mid_correction["key"]] = value
            elif field == "main_issue":
                _reset_pathway_only(session)
                session.main_issue       = value
                session.symptom_category = detect_category(value)
                session.pathway_name     = get_pathway_name(session.symptom_category)
            session.number_of_clarifications += 1
        # On no (or unclear): discard pending correction, keep original value
        session.mid_correction = None
        return

    # Priority 2: handle red-flag answer confirmation
    if session.pending_red_flag_confirm is not None:
        key = session.pending_red_flag_confirm["key"]
        if is_yes(text):
            session.pathway_answers[key] = True
            session.number_of_clarifications += 1
            session.pending_red_flag_confirm = None
        elif is_no(text):
            session.pathway_answers[key] = False
            session.pending_red_flag_confirm = None
        # else: unclear — next_bot_message re-prompts
        return

    # Phase 1: collect main issue
    if session.main_issue is None:
        corr = _extract_correction(text)
        issue = corr if corr else text
        session.main_issue       = issue
        session.symptom_category = detect_category(issue)
        session.pathway_name     = get_pathway_name(session.symptom_category)
        return

    # Phase 2: collect duration
    if session.duration is None:
        corr = _extract_correction(text)
        if corr is not None:
            dur = parse_duration(corr)
            if dur is not None:
                # Duration slot is empty → this is the first entry; apply directly.
                session.duration = dur
                return
            # Correction targets main_issue (already set) → confirm before applying.
            session.mid_correction = {"field": "main_issue", "value": corr}
            return
        parsed = parse_duration(text)
        if parsed is None:
            return   # bot re-asks
        session.duration = parsed
        return

    # Phase 3: collect severity
    if session.severity_0_10 is None:
        corr = _extract_correction(text)
        if corr is not None:
            # Check duration BEFORE severity — "3 days" has a unit so it is
            # unambiguously a duration, not a severity score.
            dur = parse_duration(corr)
            if dur is not None:
                # Duration is already set → this IS a correction; confirm before applying.
                session.mid_correction = {"field": "duration", "value": dur}
                return
            sev = parse_severity_0_10(corr)
            if sev is not None:
                # Severity slot is empty → first entry; apply directly.
                session.severity_0_10 = sev
                return
            # Correction targets main_issue (already set) → confirm before applying.
            session.mid_correction = {"field": "main_issue", "value": corr}
            return
        sev = parse_severity_0_10(text)
        if sev is None:
            return   # bot re-asks
        session.severity_0_10 = sev
        return

    # Phase 4: pathway questions
    category = session.symptom_category or "other"
    steps    = get_pathway_steps(category)

    if session.route_outcome is None:
        # Check for inline self-correction first
        corr = _extract_correction(text)
        if corr is not None:
            dur = parse_duration(corr)
            sev = parse_severity_0_10(corr)
            if dur is not None:
                # Duration is already set → correction; confirm.
                session.mid_correction = {"field": "duration", "value": dur}
            elif sev is not None:
                # Severity is already set → correction; confirm.
                session.mid_correction = {"field": "severity_0_10", "value": sev}
            elif is_yes(corr) or is_no(corr):
                last_key = _last_answered_step_key(steps, session.pathway_answers)
                if last_key:
                    session.mid_correction = {
                        "field": "pathway_answer",
                        "key": last_key,
                        "value": is_yes(corr),
                    }
            else:
                # Treat as main_issue correction; confirm.
                session.mid_correction = {"field": "main_issue", "value": corr}
            return

        # Normal yes/no pathway answer
        early = check_red_flags(category, session.pathway_answers)
        if early is None:
            pending = next_pathway_step(steps, session.pathway_answers)
            if pending is not None:
                if is_yes(text):
                    if pending.is_red_flag:
                        # Hold for one confirmation before recording
                        session.pending_red_flag_confirm = {"key": pending.key}
                    else:
                        session.pathway_answers[pending.key] = True
                elif is_no(text):
                    session.pathway_answers[pending.key] = False
                # else: unclear — bot re-asks same question
                return
        return

    # Phase 5 & 6: route decided, waiting for the patient to confirm the summary
    if not session.summary_presented:
        return   # next_bot_message will present summary on next call

    if session.summary_confirmed is None:
        if is_yes(text):
            session.summary_confirmed = True
        elif is_no(text):
            session.summary_confirmed = False
        return

    # Phase 7: patient wants to correct something — figure out which field
    if not session.summary_confirmed and session.awaiting_correction_of == "asking":
        t = text.lower()
        if any(w in t for w in ("issue", "problem", "symptom", "complaint", "condition")):
            _reset_from_issue(session)
        elif any(w in t for w in ("duration", "time", "long", "how long", "week", "day")):
            _reset_from_duration(session)
        elif any(w in t for w in ("severity", "pain", "score", "level", "number", "rating")):
            _reset_from_severity(session)
        return

    # Phase 8: done — any further input is a no-op


# Private helpers

def _find_step(session: TriageChecksheet, key: str):
    """Return the PathwayStep with the given key for the current category."""
    category = session.symptom_category or "other"
    return next(
        (s for s in get_pathway_steps(category) if s.key == key),
        None,
    )


def _strip_prompt(question: str) -> str:
    """Remove trailing '(yes/no)' from a question string."""
    return question.replace(" (yes/no)", "").rstrip()


# Reset helpers — each wipes the relevant fields when the patient corrects something

def _reset_pathway_only(session: TriageChecksheet) -> None:
    """Reset pathway state without touching duration or severity."""
    session.symptom_category          = None
    session.pathway_name              = None
    session.pathway_answers           = {}
    session.route_outcome             = None
    session.route_rationale           = None
    session.route_decided_at          = None
    session.summary_presented         = False
    session.summary_confirmed         = None
    session.awaiting_correction_of    = None
    session.mid_correction            = None
    session.pending_red_flag_confirm  = None


def _reset_from_issue(session: TriageChecksheet) -> None:
    session.main_issue                = None
    session.symptom_category          = None
    session.pathway_name              = None
    session.pathway_answers           = {}
    session.route_outcome             = None
    session.route_rationale           = None
    session.route_decided_at          = None
    session.summary_presented         = False
    session.summary_confirmed         = None
    session.awaiting_correction_of    = None
    session.mid_correction            = None
    session.pending_red_flag_confirm  = None


def _reset_from_duration(session: TriageChecksheet) -> None:
    session.duration                  = None
    session.route_outcome             = None
    session.route_rationale           = None
    session.route_decided_at          = None
    session.summary_presented         = False
    session.summary_confirmed         = None
    session.awaiting_correction_of    = None
    session.mid_correction            = None
    session.pending_red_flag_confirm  = None


def _reset_from_severity(session: TriageChecksheet) -> None:
    session.severity_0_10             = None
    session.route_outcome             = None
    session.route_rationale           = None
    session.route_decided_at          = None
    session.summary_presented         = False
    session.summary_confirmed         = None
    session.awaiting_correction_of    = None
    session.mid_correction            = None
    session.pending_red_flag_confirm  = None
