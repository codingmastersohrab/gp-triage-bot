"""
tests/test_pathways.py — Red-flag unit tests for all four symptom pathways.

Tests prove that specific answer combinations trigger the expected escalation
routes. Run with: python -m pytest tests/test_pathways.py -v

Each test drives the full handle_user_text / next_bot_message loop so the
complete dialogue engine is exercised, not just routing helpers in isolation.

NOTE ON INPUT SEQUENCES
Preamble (main_issue / duration / severity) requires NO confirmation.
Red-flag pathway questions that receive "yes" require ONE extra "yes" to
confirm before the answer is recorded (safety gate). Each affected scenario
therefore has [red_flag_yes, confirmation_yes] in its answers list.
"""
from __future__ import annotations

import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import TriageChecksheet
from app.dialogue import handle_user_text, next_bot_message


# ── Helpers ───────────────────────────────────────────────────────────────────

def _new_session() -> TriageChecksheet:
    return TriageChecksheet(
        session_id="test-session",
        created_at=datetime.now(timezone.utc),
    )


def _drive(session: TriageChecksheet, inputs: list[str]) -> str:
    """Feed a sequence of user inputs and return the last bot message."""
    bot_msg = ""
    for text in inputs:
        handle_user_text(session, text)
        bot_msg = next_bot_message(session)
    return bot_msg


def _reach_route(session: TriageChecksheet, main_issue: str, duration: str,
                 severity: str, answers: list[str]) -> str:
    """
    Drive a session through the standard preamble (issue/duration/severity),
    then supply pathway answers, and return the route_outcome.

    Preamble slots are accepted directly (no confirmation prompt).
    Red-flag "yes" answers each require one extra confirmation "yes" — include
    both in the answers list, e.g. ["yes", "yes"] for a single red-flag step.
    """
    _drive(session, [main_issue, duration, severity] + answers)
    return session.route_outcome or ""


# ── Emergency escalations ─────────────────────────────────────────────────────

def test_thunderclap_headache_emergency():
    """Thunderclap onset → subarachnoid haemorrhage screen → EMERGENCY_NOW."""
    s = _new_session()
    route = _reach_route(s, "I have a terrible headache", "1 hour", "10",
                         ["yes", "yes"])   # yes → red-flag pending; yes → confirm
    assert route == "EMERGENCY_NOW", f"Expected EMERGENCY_NOW, got {route!r}"
    assert "thunderclap" in s.route_rationale.lower()


def test_worst_ever_headache_emergency():
    """Worst-ever headache (no thunderclap) → intracranial emergency screen."""
    s = _new_session()
    route = _reach_route(s, "bad headache", "2 hours", "9",
                         ["no",          # sudden_onset = False
                          "yes", "yes"]) # worst_ever + confirm
    assert route == "EMERGENCY_NOW", f"Expected EMERGENCY_NOW, got {route!r}"


def test_headache_neurological_deficit_emergency():
    """Headache + confusion/weakness → stroke/intracranial screen."""
    s = _new_session()
    route = _reach_route(s, "headache", "1 hour", "7",
                         ["no",           # sudden_onset
                          "no",           # worst_ever
                          "yes", "yes"])  # confusion_weakness + confirm
    assert route == "EMERGENCY_NOW", f"Expected EMERGENCY_NOW, got {route!r}"


def test_chest_pain_radiating_emergency():
    """Chest pain radiating to arm/jaw → ACS screen → EMERGENCY_NOW."""
    s = _new_session()
    route = _reach_route(s, "chest pain", "1 hour", "8",
                         ["yes", "yes"])   # radiating + confirm
    assert route == "EMERGENCY_NOW", f"Expected EMERGENCY_NOW, got {route!r}"
    assert "coronary" in s.route_rationale.lower() or "cardiac" in s.route_rationale.lower()


def test_chest_pain_with_breathlessness_emergency():
    """Chest pain + breathlessness → cardiac/PE screen."""
    s = _new_session()
    route = _reach_route(s, "chest pain", "1 hour", "7",
                         ["no",          # radiating
                          "yes", "yes"]) # breathlessness + confirm
    assert route == "EMERGENCY_NOW", f"Expected EMERGENCY_NOW, got {route!r}"


def test_sob_at_rest_emergency():
    """Breathlessness at rest → respiratory/cardiac emergency."""
    s = _new_session()
    route = _reach_route(s, "I'm struggling to breathe", "1 hour", "9",
                         ["yes", "yes"])   # at_rest + confirm
    assert route == "EMERGENCY_NOW", f"Expected EMERGENCY_NOW, got {route!r}"
    assert "rest" in s.route_rationale.lower()


def test_sob_blue_lips_emergency():
    """Cyanosis (blue lips) with breathlessness → EMERGENCY_NOW."""
    s = _new_session()
    route = _reach_route(s, "difficulty breathing", "2 hours", "9",
                         ["no",          # at_rest
                          "yes", "yes"]) # blue_lips + confirm
    assert route == "EMERGENCY_NOW", f"Expected EMERGENCY_NOW, got {route!r}"
    assert "cyan" in s.route_rationale.lower()


def test_abdominal_rigid_abdomen_emergency():
    """Rigid abdomen → peritonitis screen → EMERGENCY_NOW."""
    s = _new_session()
    route = _reach_route(s, "stomach pain", "2 hours", "8",
                         ["no",          # sudden_severe
                          "yes", "yes"]) # rigid_abdomen + confirm
    assert route == "EMERGENCY_NOW", f"Expected EMERGENCY_NOW, got {route!r}"
    assert "periton" in s.route_rationale.lower()


# ── Urgent same-day escalations ───────────────────────────────────────────────

def test_headache_vision_changes_urgent():
    """Headache + visual disturbance → URGENT_SAME_DAY."""
    s = _new_session()
    route = _reach_route(s, "headache", "3 hours", "6",
                         ["no",           # sudden_onset
                          "no",           # worst_ever
                          "no",           # confusion_weakness
                          "no",           # fever → neck_stiffness skipped
                          "yes", "yes"])  # vision_changes + confirm
    assert route == "URGENT_SAME_DAY", f"Expected URGENT_SAME_DAY, got {route!r}"


def test_exertional_chest_pain_urgent():
    """Chest pain worse on exertion, no emergency flags → URGENT_SAME_DAY."""
    s = _new_session()
    route = _reach_route(s, "chest pain", "2 days", "5",
                         ["no",           # radiating
                          "no",           # breathlessness
                          "no",           # sweating_nausea
                          "no",           # sudden_severe
                          "yes", "yes"])  # exertional + confirm
    assert route == "URGENT_SAME_DAY", f"Expected URGENT_SAME_DAY, got {route!r}"


# ── Routine GP ────────────────────────────────────────────────────────────────

def test_mild_headache_routine():
    """Headache with all red flags negative → ROUTINE_GP."""
    s = _new_session()
    route = _reach_route(s, "mild headache", "2 days", "3",
                         ["no",   # sudden_onset
                          "no",   # worst_ever
                          "no",   # confusion_weakness
                          "no",   # fever  (neck_stiffness skipped)
                          "no",   # vision_changes
                          "no"])  # head_injury
    assert route == "ROUTINE_GP", f"Expected ROUTINE_GP, got {route!r}"


def test_stomach_ache_no_red_flags_routine():
    """Stomach ache, all pathway answers negative → ROUTINE_GP."""
    s = _new_session()
    route = _reach_route(s, "stomach ache", "1 day", "4",
                         ["no",   # sudden_severe
                          "no",   # rigid_abdomen
                          "no",   # pregnancy_possible  → ectopic_risk skipped
                          "no",   # blood_in_stool_vomit
                          "no",   # fever
                          "no"])  # vomiting_diarrhoea
    assert route == "ROUTINE_GP", f"Expected ROUTINE_GP, got {route!r}"


# ── Category detection ────────────────────────────────────────────────────────

def test_category_detection():
    from app.pathways import detect_category
    assert detect_category("I have a terrible headache")         == "headache"
    assert detect_category("chest pain and tightness")           == "chest_pain"
    assert detect_category("stomach ache and nausea")            == "abdominal_pain"
    assert detect_category("I'm struggling to breathe")          == "shortness_of_breath"
    assert detect_category("sore toe")                           == "other"


# ── Red-flag confirmation gate ────────────────────────────────────────────────

def test_red_flag_yes_held_for_confirmation():
    """'yes' to a red-flag step sets pending_red_flag_confirm before recording."""
    s = _new_session()
    handle_user_text(s, "chest pain"); next_bot_message(s)
    handle_user_text(s, "1 hour");    next_bot_message(s)
    handle_user_text(s, "8");         next_bot_message(s)

    # First "yes" — answer held, not yet recorded
    handle_user_text(s, "yes")
    assert s.pending_red_flag_confirm is not None
    assert s.pending_red_flag_confirm["key"] == "radiating"
    assert "radiating" not in s.pathway_answers
    assert s.route_outcome is None

    msg = next_bot_message(s)
    assert "confirm" in msg.lower()
    assert "yes" in msg.lower()

    # Confirm: answer recorded, route computed on next next_bot_message call
    handle_user_text(s, "yes")
    assert s.pending_red_flag_confirm is None
    assert s.pathway_answers.get("radiating") is True
    next_bot_message(s)
    assert s.route_outcome == "EMERGENCY_NOW"


def test_red_flag_confirmation_rejected_continues():
    """Saying 'no' to red-flag confirmation records False and asks next question."""
    s = _new_session()
    handle_user_text(s, "chest pain"); next_bot_message(s)
    handle_user_text(s, "1 hour");    next_bot_message(s)
    handle_user_text(s, "8");         next_bot_message(s)

    handle_user_text(s, "yes")    # tentative yes to radiating (red flag)
    next_bot_message(s)            # confirmation prompt

    handle_user_text(s, "no")     # reject confirmation → records False
    assert s.pending_red_flag_confirm is None
    assert s.pathway_answers.get("radiating") is False
    assert s.route_outcome is None  # no escalation

    msg = next_bot_message(s)
    assert "?" in msg              # next pathway question asked


def test_red_flag_ambiguous_answer_reprompts():
    """An unclear answer during red-flag confirmation does not advance state."""
    s = _new_session()
    handle_user_text(s, "chest pain"); next_bot_message(s)
    handle_user_text(s, "1 hour");    next_bot_message(s)
    handle_user_text(s, "8");         next_bot_message(s)

    handle_user_text(s, "yes")    # tentative yes
    key_before = s.pending_red_flag_confirm["key"]

    handle_user_text(s, "maybe")  # unclear — should not advance
    assert s.pending_red_flag_confirm is not None
    assert s.pending_red_flag_confirm["key"] == key_before
    assert "radiating" not in s.pathway_answers


# ── Summary confirmation flow ─────────────────────────────────────────────────

def test_summary_confirmation_marks_complete():
    """After routing, confirming summary sets summary_confirmed=True."""
    s = _new_session()
    _reach_route(s, "headache", "1 day", "5",
                 ["no", "no", "no", "no", "no", "no"])  # all no → ROUTINE_GP
    assert s.route_outcome == "ROUTINE_GP"
    assert s.summary_presented is True
    assert s.summary_confirmed is None

    handle_user_text(s, "yes")
    next_bot_message(s)
    assert s.summary_confirmed is True


def test_summary_correction_resets_duration():
    """Saying no to summary then 'duration' resets duration slot."""
    s = _new_session()
    _reach_route(s, "headache", "1 day", "5",
                 ["no", "no", "no", "no", "no", "no"])

    handle_user_text(s, "no")          # reject summary
    next_bot_message(s)                # sets awaiting_correction_of="asking"
    handle_user_text(s, "duration")    # correct duration
    assert s.duration is None
    assert s.summary_confirmed is None
    assert s.route_outcome is None     # reset so pathway re-runs


# ── Mid-session inline correction ─────────────────────────────────────────────

def test_inline_duration_correction():
    """'I meant 1 day' during pathway questions triggers one-time confirmation."""
    s = _new_session()
    handle_user_text(s, "headache"); next_bot_message(s)
    handle_user_text(s, "2 days");   next_bot_message(s)
    handle_user_text(s, "4");        next_bot_message(s)
    assert s.duration.value == 2

    handle_user_text(s, "I meant 1 day")
    assert s.mid_correction is not None
    assert s.mid_correction["field"] == "duration"
    msg = next_bot_message(s)
    assert "1" in msg and "day" in msg

    handle_user_text(s, "yes")
    assert s.duration.value == 1
    assert s.mid_correction is None


def test_inline_duration_correction_rejected():
    """Saying 'no' to the correction prompt keeps the original value."""
    s = _new_session()
    handle_user_text(s, "headache"); next_bot_message(s)
    handle_user_text(s, "2 days");   next_bot_message(s)
    handle_user_text(s, "4");        next_bot_message(s)

    handle_user_text(s, "I meant 3 days")
    next_bot_message(s)
    handle_user_text(s, "no")
    assert s.duration.value == 2   # original kept
    assert s.mid_correction is None


def test_inline_pathway_answer_correction():
    """'I meant yes' after a 'no' answer corrects the last pathway answer."""
    s = _new_session()
    handle_user_text(s, "mild headache"); next_bot_message(s)
    handle_user_text(s, "2 days");        next_bot_message(s)
    handle_user_text(s, "3");             next_bot_message(s)

    # Answer sudden_onset = no
    handle_user_text(s, "no")
    next_bot_message(s)   # asks worst_ever

    # Correct: "I meant yes"
    handle_user_text(s, "I meant yes")
    assert s.mid_correction is not None
    assert s.mid_correction["field"] == "pathway_answer"
    assert s.mid_correction["key"] == "sudden_onset"
    assert s.mid_correction["value"] is True

    msg = next_bot_message(s)
    assert "check" in msg.lower() or "confirm" in msg.lower()

    # Confirm the correction
    handle_user_text(s, "yes")
    assert s.pathway_answers.get("sudden_onset") is True
    assert s.mid_correction is None


def test_correction_during_severity_phase_asks_confirmation():
    """
    'I meant 3 days' said while bot is waiting for severity must:
      1. Set mid_correction (not apply immediately — old bug was direct apply).
      2. Show a confirmation prompt even though severity is still None.
      3. Only apply the new duration after the user says 'yes'.
      4. Then resume asking for severity.
    Works identically for voice (same code path).
    """
    s = _new_session()
    handle_user_text(s, "headache"); next_bot_message(s)   # main issue
    handle_user_text(s, "2 days");   next_bot_message(s)   # duration = 2
    # Bot now asks for severity, but user corrects duration instead
    handle_user_text(s, "I meant 3 days")

    # Correction is held — NOT applied yet (this was the bug: it used to apply immediately)
    assert s.duration.value == 2,    "Duration must not change until confirmed"
    assert s.severity_0_10 is None
    assert s.mid_correction is not None
    assert s.mid_correction["field"] == "duration"

    # next_bot_message must show the confirmation, NOT the severity question
    msg = next_bot_message(s)
    assert "3" in msg and "day" in msg, f"Expected confirmation mentioning '3 days', got: {msg!r}"
    assert "check" in msg.lower() or "confirm" in msg.lower()

    # User confirms
    handle_user_text(s, "yes")
    assert s.duration.value == 3,    "Duration must be updated after confirmation"
    assert s.mid_correction is None

    # Bot now asks for severity
    msg = next_bot_message(s)
    assert "severe" in msg.lower() or "scale" in msg.lower(), \
        f"Expected severity question, got: {msg!r}"
    assert s.severity_0_10 is None


def test_correction_during_pathway_phase_asks_confirmation():
    """
    'I meant 7' (severity correction) sent during pathway questions:
      • Correction set → confirmation shown → applied → pathway resumes.
    Covers: correction after bot has moved on (regression for screenshot #1 bug).
    """
    s = _new_session()
    handle_user_text(s, "headache"); next_bot_message(s)
    handle_user_text(s, "2 days");   next_bot_message(s)
    handle_user_text(s, "5");        next_bot_message(s)
    # Now in pathway phase — user corrects severity
    handle_user_text(s, "I meant 7")

    assert s.severity_0_10 == 5,   "Severity must not change until confirmed"
    assert s.mid_correction is not None
    assert s.mid_correction["field"] == "severity_0_10"

    msg = next_bot_message(s)
    assert "7" in msg
    assert "check" in msg.lower() or "confirm" in msg.lower()

    handle_user_text(s, "yes")
    assert s.severity_0_10 == 7
    assert s.mid_correction is None

    # Next message is the next pathway question (not severity again)
    msg = next_bot_message(s)
    assert "yes/no" in msg.lower() or "?" in msg


def test_voice_correction_same_code_path():
    """
    Voice transcripts arrive via the same /user_input handler (same handle_user_text).
    A voice transcript containing 'I meant 3 days' must trigger mid_correction,
    exactly as typed input does.
    """
    s = _new_session()
    handle_user_text(s, "headache"); next_bot_message(s)
    handle_user_text(s, "1 week");   next_bot_message(s)
    handle_user_text(s, "6");        next_bot_message(s)
    # Simulate a voice transcript that is a correction
    voice_transcript = "I meant 3 days"
    handle_user_text(s, voice_transcript)   # same handler as typed

    # duration is Duration(value=1, unit=weeks) — unchanged until confirmed
    assert s.duration.value == 1
    assert s.mid_correction is not None
    assert s.mid_correction["field"] == "duration"

    msg = next_bot_message(s)
    assert "3" in msg and "day" in msg


def test_mid_correction_duration_survives_db_roundtrip():
    """
    When mid_correction is saved to the DB and reloaded, Duration inside
    mid_correction["value"] comes back as a plain dict.  Both next_bot_message
    and handle_user_text must coerce it back to Duration so store.py doesn't
    crash on .value / .unit.value.

    Reproduces the 'Load failed' bug: user said 'I meant 3 days', bot asked
    confirmation, user said 'yes' → 500 AttributeError on session.duration.unit.
    """
    s = _new_session()
    handle_user_text(s, "headache"); next_bot_message(s)
    handle_user_text(s, "2 days");   next_bot_message(s)
    handle_user_text(s, "5");        next_bot_message(s)
    handle_user_text(s, "I meant 3 days")
    assert s.mid_correction["field"] == "duration"

    # Simulate DB round-trip: value becomes a plain dict
    json_blob = s.model_dump_json()
    s2 = TriageChecksheet.model_validate_json(json_blob)
    assert isinstance(s2.mid_correction["value"], dict), \
        "Sanity: after JSON round-trip the value is a plain dict"

    # next_bot_message must not crash
    msg = next_bot_message(s2)
    assert "3" in msg and "day" in msg

    # handle_user_text 'yes' must apply Duration correctly (not leave a raw dict)
    handle_user_text(s2, "yes")
    assert s2.mid_correction is None
    from app.models import Duration
    assert isinstance(s2.duration, Duration), "session.duration must be Duration, not dict"
    assert s2.duration.value == 3
