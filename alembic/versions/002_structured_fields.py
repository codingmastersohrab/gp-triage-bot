"""002_structured_fields: add queryable structured columns to sessions table.

New columns on sessions:
  symptom_category, main_issue, duration_value, duration_unit,
  severity_score, red_flags_list, completed_at, pathway_name,
  pathway_version, number_of_turns

Backfills existing rows by parsing the stored JSON blob.

Revision ID: 002
Revises: 001
Create Date: 2026-03-10
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision      = "002"
down_revision = "001"
branch_labels = None
depends_on    = None

_NOW = datetime.now(timezone.utc).isoformat()

_NEW_COLS = [
    ("symptom_category",  sa.Text(),     True),
    ("main_issue",        sa.Text(),     True),
    ("duration_value",    sa.Integer(),  True),
    ("duration_unit",     sa.Text(),     True),
    ("severity_score",    sa.Text(),     True),
    ("red_flags_list",    sa.Text(),     True),
    ("completed_at",      sa.DateTime(), True),
    ("pathway_name",      sa.Text(),     True),
    ("pathway_version",   sa.Integer(),  True),
    ("number_of_turns",   sa.Integer(),  True),
]


def upgrade() -> None:
    conn      = op.get_bind()
    inspector = sa.inspect(conn)
    existing  = {c["name"] for c in inspector.get_columns("sessions")}

    missing = [
        sa.Column(name, typ, nullable=nullable)
        for name, typ, nullable in _NEW_COLS
        if name not in existing
    ]

    if missing:
        with op.batch_alter_table("sessions", recreate="auto") as batch_op:
            for col in missing:
                batch_op.add_column(col)

    # Backfill from JSON blob
    rows = conn.execute(
        sa.text("SELECT session_id, data FROM sessions WHERE symptom_category IS NULL OR main_issue IS NULL")
    ).fetchall()

    for session_id, raw_data in rows:
        try:
            data = json.loads(raw_data)

            symptom_category = data.get("symptom_category")
            main_issue       = data.get("main_issue")
            pathway_name     = data.get("pathway_name")
            pathway_version  = data.get("pathway_version", 1)
            number_of_turns  = data.get("number_of_turns", 0)
            severity_score   = str(data["severity_0_10"]) if data.get("severity_0_10") is not None else None

            dur = data.get("duration")
            duration_value = dur.get("value") if isinstance(dur, dict) else None
            duration_unit  = dur.get("unit") if isinstance(dur, dict) else None

            # red_flags_list: prefer pathway_answers, fall back to old red_flags
            pathway_answers = data.get("pathway_answers") or data.get("red_flags") or {}
            red_flags_list  = json.dumps(pathway_answers) if pathway_answers else None

            # completed_at: set if session was routed and summary confirmed
            route    = data.get("route_outcome")
            complete = data.get("summary_confirmed")
            completed_at = _NOW if (route in ("EMERGENCY_NOW", "URGENT_SAME_DAY", "ROUTINE_GP") and complete is True) else None

        except Exception:
            symptom_category = None
            main_issue       = None
            pathway_name     = None
            pathway_version  = 1
            number_of_turns  = 0
            severity_score   = None
            duration_value   = None
            duration_unit    = None
            red_flags_list   = None
            completed_at     = None

        conn.execute(
            sa.text(
                "UPDATE sessions SET "
                "symptom_category=:sc, main_issue=:mi, "
                "duration_value=:dv, duration_unit=:du, "
                "severity_score=:ss, red_flags_list=:rfl, "
                "completed_at=:ca, pathway_name=:pn, "
                "pathway_version=:pv, number_of_turns=:nt "
                "WHERE session_id=:sid"
            ),
            {
                "sc":  symptom_category,
                "mi":  main_issue,
                "dv":  duration_value,
                "du":  duration_unit,
                "ss":  severity_score,
                "rfl": red_flags_list,
                "ca":  completed_at,
                "pn":  pathway_name,
                "pv":  pathway_version,
                "nt":  number_of_turns,
                "sid": session_id,
            },
        )


def downgrade() -> None:
    # SQLite: use batch to remove columns
    cols_to_remove = [name for name, _, _ in _NEW_COLS]
    with op.batch_alter_table("sessions", recreate="always") as batch_op:
        for col in cols_to_remove:
            try:
                batch_op.drop_column(col)
            except Exception:
                pass
