from __future__ import annotations

from typing import Any, Dict

from app.models import TriageChecksheet


# Structured summary (used by the API and for clinician handover)

def generate_triage_summary(session: TriageChecksheet) -> Dict[str, Any]:
    """
    Deterministic, non-diagnostic summary for handover/audit.
    Only uses captured fields; does not infer medical conclusions.
    """
    duration_str = None
    if session.duration is not None:
        duration_str = f"{session.duration.value} {session.duration.unit.value}"

    # Collect positive findings from both pathway_answers (new) and legacy red_flags
    positive_flags = [k for k, v in session.pathway_answers.items() if v is True]
    if not positive_flags:
        positive_flags = [k for k, v in session.red_flags.items() if v is True]

    return {
        "session_id":       session.session_id,
        "created_at":       session.created_at.isoformat(),
        "main_issue":       session.main_issue,
        "symptom_category": session.symptom_category,
        "pathway_name":     session.pathway_name,
        "duration":         duration_str,
        "severity_0_10":    session.severity_0_10,
        "positive_findings": positive_flags,
        "pathway_answers":  session.pathway_answers,
        "route_outcome":    session.route_outcome,
        "route_rationale":  session.route_rationale,
        "route_decided_at": session.route_decided_at.isoformat() if session.route_decided_at else None,
        "confirmed_fields": [k for k, v in session.confirmed.items() if v is True],
        "summary_confirmed": session.summary_confirmed,
        "number_of_turns":  session.number_of_turns,
    }


def generate_summary_text(session: TriageChecksheet) -> str:
    """Clinician-facing plain-text summary (used by GET /session/{id}/summary)."""
    s = generate_triage_summary(session)

    lines = ["Triage summary (non-clinical intake):"]
    lines.append(f"- Main issue: {s['main_issue'] or 'Not captured'}")

    if s["symptom_category"]:
        lines.append(f"- Symptom category: {s['symptom_category']} (pathway: {s['pathway_name']})")

    lines.append(f"- Duration: {s['duration'] or 'Not captured'}")
    lines.append(
        f"- Severity (0\u201310): {s['severity_0_10']}" if s["severity_0_10"] is not None
        else "- Severity (0\u201310): Not captured"
    )

    if s["positive_findings"]:
        formatted = ", ".join(k.replace("_", " ") for k in s["positive_findings"])
        lines.append(f"- Positive findings: {formatted}")
    else:
        lines.append("- Positive findings: None reported")

    if s["route_outcome"]:
        lines.append(f"- Routing outcome: {s['route_outcome']}")
        lines.append(f"- Routing rationale: {s['route_rationale']}")
    else:
        lines.append("- Routing outcome: Not finalised")

    lines.append(f"- Turns taken: {s['number_of_turns']}")
    lines.append(
        "- Note: This system does not diagnose or prescribe. "
        "If symptoms worsen, seek urgent help (NHS\u00a0111 or 999)."
    )
    return "\n".join(lines)


# Patient-facing summary shown in chat for confirmation

_ROUTE_LABEL: Dict[str, str] = {
    "EMERGENCY_NOW":    "\u26a0\ufe0f  Seek emergency care NOW \u2014 call 999 or go to A&E immediately.",
    "URGENT_SAME_DAY":  "Seek same-day GP or urgent care review today.",
    "ROUTINE_GP":       "A routine GP appointment is appropriate.",
    "INCOMPLETE":       "More information is needed to route you safely.",
}


def generate_patient_summary(session: TriageChecksheet) -> str:
    """
    Friendly end-of-interaction summary presented to the patient in chat,
    asking them to confirm before the session is finalised.
    """
    lines = ["Here\u2019s what I\u2019ve recorded:"]

    lines.append(f"  \u2022 Main concern: {session.main_issue or 'not captured'}")

    if session.duration:
        lines.append(f"  \u2022 Duration: {session.duration.value} {session.duration.unit.value}")
    else:
        lines.append("  \u2022 Duration: not captured")

    if session.severity_0_10 is not None:
        lines.append(f"  \u2022 Severity: {session.severity_0_10}/10")

    positives = [
        k.replace("_", " ")
        for k, v in session.pathway_answers.items()
        if v is True
    ]
    if positives:
        lines.append(f"  \u2022 Symptoms noted: {', '.join(positives)}")

    route = session.route_outcome or "INCOMPLETE"
    lines.append("")
    lines.append(_ROUTE_LABEL.get(route, route))

    if session.route_rationale:
        lines.append(f"  (Reason: {session.route_rationale})")

    lines.append("")
    lines.append("Does this summary look correct? (yes / no)")
    lines.append("")
    lines.append(
        "Note: This system does not diagnose. "
        "If symptoms worsen, call NHS\u00a0111 or 999 in an emergency."
    )
    return "\n".join(lines)


def generate_completion_message(session: TriageChecksheet) -> str:
    """Final message after the patient confirms the summary."""
    route = session.route_outcome

    if route == "EMERGENCY_NOW":
        return (
            "Thank you for confirming. "
            "Please call 999 or go to A&E immediately \u2014 do not wait. "
            "Your details have been recorded for your GP practice. "
            "This system does not diagnose; please follow the advice of emergency services."
        )
    if route == "URGENT_SAME_DAY":
        return (
            "Thank you for confirming. "
            "Please contact your GP practice first thing today or attend an urgent care centre. "
            "Your details have been recorded. "
            "If your condition worsens before you are seen, call 999."
        )
    # ROUTINE_GP / INCOMPLETE fallback
    return (
        "Thank you for confirming. "
        "Your GP practice will be in touch to arrange an appointment. "
        "Your details have been recorded. "
        "If symptoms worsen before your appointment, contact NHS\u00a0111 or call 999 in an emergency."
    )
