from __future__ import annotations

from typing import Dict, Any

from app.models import TriageChecksheet


def generate_triage_summary(session: TriageChecksheet) -> Dict[str, Any]:
    """
    Deterministic, non-diagnostic summary for handover/audit.
    Only uses captured fields; does not infer medical conclusions.
    """
    duration_str = None
    if session.duration is not None:
        duration_str = f"{session.duration.value} {session.duration.unit.value}"

    red_flags = []
    for k, v in session.red_flags.items():
        if v is True:
            red_flags.append(k)

    summary = {
        "session_id": session.session_id,
        "created_at": session.created_at.isoformat(),
        "main_issue": session.main_issue,
        "duration": duration_str,
        "severity_0_10": session.severity_0_10,
        "red_flags_true": red_flags,
        "route_outcome": session.route_outcome,
        "route_rationale": session.route_rationale,
        "confirmed_fields": [k for k, v in session.confirmed.items() if v is True],
    }
    return summary


def generate_summary_text(session: TriageChecksheet) -> str:
    s = generate_triage_summary(session)

    lines = []
    lines.append("Triage summary (non-clinical intake):")
    lines.append(f"- Main issue: {s['main_issue'] or 'Not captured'}")

    if s["duration"] is not None:
        lines.append(f"- Duration: {s['duration']}")
    else:
        lines.append("- Duration: Not captured")

    if s["severity_0_10"] is not None:
        lines.append(f"- Severity (0–10): {s['severity_0_10']}")
    else:
        lines.append("- Severity (0–10): Not captured")

    if s["red_flags_true"]:
        lines.append(f"- Red flags (reported): {', '.join(s['red_flags_true'])}")
    else:
        lines.append("- Red flags (reported): None in asked set")

    if s["route_outcome"]:
        lines.append(f"- Routing outcome: {s['route_outcome']}")
        lines.append(f"- Routing rationale: {s['route_rationale']}")
    else:
        lines.append("- Routing outcome: Not finalised")

    lines.append("- Note: This system does not diagnose or prescribe. If symptoms worsen or severe symptoms develop, seek urgent help (NHS 111 or 999 in an emergency).")
    return "\n".join(lines)
