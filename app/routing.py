from __future__ import annotations

from typing import Dict, List, Tuple

from app.models import TriageChecksheet


# MVP red flags (keep small and explicit)
RED_FLAG_QUESTIONS: List[Tuple[str, str]] = [
    ("severe_breathing_difficulty", "Are you having severe difficulty breathing right now? (yes/no)"),
    ("chest_pain", "Are you having chest pain right now? (yes/no)"),
    ("stroke_signs", "Do you have signs of a stroke right now, like face drooping, arm weakness, or speech problems? (yes/no)"),
]


EMERGENCY_KEYS = {"severe_breathing_difficulty", "chest_pain", "stroke_signs"}


def initialise_red_flags(session: TriageChecksheet) -> None:
    """
    Ensure all red flag keys exist with tri-state None/True/False.
    """
    for key, _q in RED_FLAG_QUESTIONS:
        session.red_flags.setdefault(key, None)


def compute_route(session: TriageChecksheet) -> tuple[str, str]:
    """
    Deterministic routing for MVP.
    """
    initialise_red_flags(session)

    for key in EMERGENCY_KEYS:
        if session.red_flags.get(key) is True:
            return ("EMERGENCY_NOW", f"Red flag triggered: {key}")

    # If any red flags still unknown, we can't finalise—treat as needs more questions
    if any(session.red_flags.get(k) is None for k, _ in RED_FLAG_QUESTIONS):
        return ("INCOMPLETE", "Awaiting red-flag answers")

    return ("ROUTINE_GP", "No emergency red flags reported in MVP set")


def next_red_flag_to_ask(session: TriageChecksheet) -> tuple[str, str] | None:
    initialise_red_flags(session)
    for key, question in RED_FLAG_QUESTIONS:
        if session.red_flags.get(key) is None:
            return (key, question)
    return None
