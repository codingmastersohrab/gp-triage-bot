from __future__ import annotations
from app.routing import compute_route, next_red_flag_to_ask, initialise_red_flags

from dataclasses import dataclass

from app.models import TriageChecksheet
from app.parsers import parse_duration, parse_severity_0_10



@dataclass
class BotTurn:
    message: str


def is_yes(text: str) -> bool:
    t = text.strip().lower()
    return t in {"yes", "y", "yeah", "yep", "correct", "right", "that's right", "thats right", "ok", "okay"}


def is_no(text: str) -> bool:
    t = text.strip().lower()
    return t in {"no", "n", "nope", "nah", "not really", "incorrect", "wrong"}


def next_bot_message(session: TriageChecksheet) -> str:
    if session.main_issue is None:
        return "What’s the main issue you’re calling about today? (One sentence is fine.)"

    if not session.confirmed.get("main_issue", False):
        return f"Just to check, you said: “{session.main_issue}”. Is that correct? (yes/no)"

    if session.duration is None:
        return "How long has this been going on? (e.g., ‘2 days’, ‘a week’)"

    if not session.confirmed.get("duration", False):
        d = session.duration
        return f"Just to check, you said: {d.value} {d.unit.value}. Is that correct? (yes/no)"

    # NEW: Severity prompts (this must come BEFORE any final return)
    if session.severity_0_10 is None:
        return "How severe is it right now from 0 to 10, where 10 is the worst you can imagine?"

    if not session.confirmed.get("severity_0_10", False):
        return f"Just to check, you said the severity is {session.severity_0_10} out of 10. Is that correct? (yes/no)"

        # Red flag checks (MVP)
    initialise_red_flags(session)
    pending = next_red_flag_to_ask(session)
    if pending is not None:
        _key, question = pending
        return question

    # If all red flags answered, compute route and return safe templated guidance
    outcome, rationale = compute_route(session)
    session.route_outcome = outcome
    session.route_rationale = rationale

    if outcome == "EMERGENCY_NOW":
        return (
            "Based on what you’ve told me, this may need urgent help now. "
            "If this is an emergency or you feel very unwell, call 999 or go to A&E now. "
            "I’m not a clinician and can’t diagnose—this is to help route you safely."
        )

    if outcome == "ROUTINE_GP":
        return (
            "Thanks — I’ve captured the key details for the practice. "
            "A routine GP contact is likely appropriate. "
            "If symptoms get worse or you develop new severe symptoms, seek urgent help (NHS 111 or 999 in an emergency)."
        )

    return "Thanks — I need a bit more information to route you safely."




def handle_user_text(session: TriageChecksheet, user_text: str) -> None:
    text = user_text.strip()

    # Collect main issue
    if session.main_issue is None:
        session.main_issue = text
        session.confirmed["main_issue"] = False
        return

    # Confirm/correct main issue
    if not session.confirmed.get("main_issue", False):
        if is_yes(text):
            session.confirmed["main_issue"] = True
            return
        if is_no(text):
            session.main_issue = None
            session.confirmed["main_issue"] = False
            return
        session.main_issue = text
        session.confirmed["main_issue"] = False
        return

    # Collect duration
    if session.duration is None:
        parsed = parse_duration(text)
        if parsed is None:
            return
        session.duration = parsed
        session.confirmed["duration"] = False
        return

    # Confirm/correct duration
    if not session.confirmed.get("duration", False):
        if is_yes(text):
            session.confirmed["duration"] = True
            return
        if is_no(text):
            session.duration = None
            session.confirmed["duration"] = False
            return

        parsed = parse_duration(text)
        if parsed is None:
            session.duration = None
            session.confirmed["duration"] = False
            return
        session.duration = parsed
        session.confirmed["duration"] = False
        return

    # Collect severity
    if session.severity_0_10 is None:
        sev = parse_severity_0_10(text)
        if sev is None:
            return
        session.severity_0_10 = sev
        session.confirmed["severity_0_10"] = False
        return

    # Confirm/correct severity
    if not session.confirmed.get("severity_0_10", False):
        if is_yes(text):
            session.confirmed["severity_0_10"] = True
            return
        if is_no(text):
            session.severity_0_10 = None
            session.confirmed["severity_0_10"] = False
            return

        sev = parse_severity_0_10(text)
        if sev is None:
            session.severity_0_10 = None
            session.confirmed["severity_0_10"] = False
            return
        session.severity_0_10 = sev
        session.confirmed["severity_0_10"] = False
        return

    # Collect red-flag yes/no answers
    initialise_red_flags(session)
    pending = next_red_flag_to_ask(session)
    if pending is None:
        return  # done

    key, _question = pending
    if is_yes(text):
        session.red_flags[key] = True
        return
    if is_no(text):
        session.red_flags[key] = False
        return
    # If unclear, do nothing; bot will re-ask
    return
