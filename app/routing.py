"""
Deterministic routing based on the patient's pathway answers.

There are four possible outcomes:
  EMERGENCY_NOW   - at least one emergency red flag was triggered
  URGENT_SAME_DAY - at least one urgent red flag was triggered, but no emergency ones
  ROUTINE_GP      - all pathway questions answered with no red flags found
  INCOMPLETE      - there are still unanswered pathway questions

DISCLAIMER: rule-based prototype; not NHS Pathways compliant.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from app.models import TriageChecksheet
from app.pathways import check_red_flags, get_pathway_steps, next_pathway_step

# Legacy constants kept for backward compatibility with old sessions
RED_FLAG_QUESTIONS: List[Tuple[str, str]] = [
    ("severe_breathing_difficulty", "Are you having severe difficulty breathing right now? (yes/no)"),
    ("chest_pain", "Are you having chest pain right now? (yes/no)"),
    ("stroke_signs", "Do you have signs of a stroke right now, like face drooping, arm weakness, or speech problems? (yes/no)"),
]
EMERGENCY_KEYS = {"severe_breathing_difficulty", "chest_pain", "stroke_signs"}


def initialise_red_flags(session: TriageChecksheet) -> None:
    """Legacy helper — kept so old code paths don't break."""
    for key, _q in RED_FLAG_QUESTIONS:
        session.red_flags.setdefault(key, None)


def next_red_flag_to_ask(session: TriageChecksheet) -> tuple[str, str] | None:
    """Legacy helper — kept so old code paths don't break."""
    initialise_red_flags(session)
    for key, question in RED_FLAG_QUESTIONS:
        if session.red_flags.get(key) is None:
            return (key, question)
    return None


# Primary routing

def compute_route(session: TriageChecksheet) -> tuple[str, str]:
    """
    Compute routing outcome from pathway answers.

    Precedence:
      1. Any EMERGENCY_NOW red flag triggered → EMERGENCY_NOW
      2. Any URGENT_SAME_DAY red flag triggered → URGENT_SAME_DAY
      3. All questions answered, no red flags → ROUTINE_GP
      4. Questions still pending → INCOMPLETE
    """
    category = session.symptom_category or "other"
    answers  = session.pathway_answers

    # Check for triggered red flags
    result = check_red_flags(category, answers)
    if result is not None:
        return result

    # Check whether all applicable questions have been answered
    steps   = get_pathway_steps(category)
    pending = next_pathway_step(steps, answers)
    if pending is not None:
        return ("INCOMPLETE", "Awaiting remaining pathway questions")

    return (
        "ROUTINE_GP",
        f"No red flags identified in {category} pathway — routine appointment recommended",
    )
