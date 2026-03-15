"""initial_schema: sessions table upgrade + messages table

Handles two cases:
  A) Fresh database (no tables) — creates both tables from scratch.
  B) Existing database with old schema (sessions has only session_id + data)
     — adds new columns to sessions via batch ALTER, backfills metadata from
     the stored JSON blob, then creates the messages table.

If the database already has the new schema (e.g. created by app startup
via create_all()), this migration is a no-op.

Revision ID: 001
Revises:
Create Date: 2026-03-06
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "001"
down_revision = None
branch_labels = None
depends_on = None

_NOW = datetime.now(timezone.utc).isoformat()


# ── helpers ───────────────────────────────────────────────────────────────────

def _col_names(inspector, table: str) -> set[str]:
    return {c["name"] for c in inspector.get_columns(table)}


# ── upgrade ───────────────────────────────────────────────────────────────────

def upgrade() -> None:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = set(inspector.get_table_names())

    # ── 1. sessions table ─────────────────────────────────────────────────────
    if "sessions" not in existing_tables:
        # Case A: fresh install — create full schema
        op.create_table(
            "sessions",
            sa.Column("session_id",           sa.String(),     primary_key=True),
            sa.Column("data",                 sa.Text(),       nullable=False),
            sa.Column("created_at",           sa.DateTime(),   nullable=True),
            sa.Column("updated_at",           sa.DateTime(),   nullable=True),
            sa.Column("status",               sa.String(20),   nullable=False, server_default="active"),
            sa.Column("schema_version",       sa.Integer(),    nullable=False, server_default="1"),
            sa.Column("routing_outcome",      sa.Text(),       nullable=True),
            sa.Column("routing_rationale",    sa.Text(),       nullable=True),
            sa.Column("red_flags_present",    sa.Integer(),    nullable=True),
            sa.Column("summary_text_snapshot",sa.Text(),       nullable=True),
            sa.CheckConstraint(
                "status IN ('active', 'completed', 'abandoned')",
                name="ck_sessions_status",
            ),
        )
    else:
        # Case B or already-upgraded: add any missing columns
        existing_cols = _col_names(inspector, "sessions")
        new_cols = []

        if "created_at"            not in existing_cols:
            new_cols.append(sa.Column("created_at",            sa.DateTime(),  nullable=True))
        if "updated_at"            not in existing_cols:
            new_cols.append(sa.Column("updated_at",            sa.DateTime(),  nullable=True))
        if "status"                not in existing_cols:
            new_cols.append(sa.Column("status",                sa.String(20),  nullable=False, server_default="active"))
        if "schema_version"        not in existing_cols:
            new_cols.append(sa.Column("schema_version",        sa.Integer(),   nullable=False, server_default="1"))
        if "routing_outcome"       not in existing_cols:
            new_cols.append(sa.Column("routing_outcome",       sa.Text(),      nullable=True))
        if "routing_rationale"     not in existing_cols:
            new_cols.append(sa.Column("routing_rationale",     sa.Text(),      nullable=True))
        if "red_flags_present"     not in existing_cols:
            new_cols.append(sa.Column("red_flags_present",     sa.Integer(),   nullable=True))
        if "summary_text_snapshot" not in existing_cols:
            new_cols.append(sa.Column("summary_text_snapshot", sa.Text(),      nullable=True))

        if new_cols:
            with op.batch_alter_table("sessions", recreate="auto") as batch_op:
                for col in new_cols:
                    batch_op.add_column(col)

        # ── Backfill: populate new metadata columns from the stored JSON ──────
        # Only rows where created_at is NULL (i.e. written by the old store)
        rows = conn.execute(
            sa.text("SELECT session_id, data FROM sessions WHERE created_at IS NULL")
        ).fetchall()

        for session_id, raw_data in rows:
            try:
                data = json.loads(raw_data)
                created_at      = data.get("created_at", _NOW)
                route_outcome   = data.get("route_outcome")
                route_rationale = data.get("route_rationale")
                red_flags: dict = data.get("red_flags", {})

                if any(v is True for v in red_flags.values()):
                    red_flags_present = 1
                elif red_flags and all(v is not None for v in red_flags.values()):
                    red_flags_present = 0
                else:
                    red_flags_present = None

                status = (
                    "completed"
                    if route_outcome in ("EMERGENCY_NOW", "ROUTINE_GP")
                    else "active"
                )
            except Exception:
                created_at        = _NOW
                route_outcome     = None
                route_rationale   = None
                red_flags_present = None
                status            = "active"

            conn.execute(
                sa.text(
                    "UPDATE sessions "
                    "SET created_at=:ca, updated_at=:ua, status=:st, "
                    "schema_version=1, routing_outcome=:ro, routing_rationale=:rr, "
                    "red_flags_present=:rfp "
                    "WHERE session_id=:sid"
                ),
                {
                    "ca":  created_at,
                    "ua":  _NOW,
                    "st":  status,
                    "ro":  route_outcome,
                    "rr":  route_rationale,
                    "rfp": red_flags_present,
                    "sid": session_id,
                },
            )

    # ── 2. messages table ─────────────────────────────────────────────────────
    if "messages" not in existing_tables:
        op.create_table(
            "messages",
            sa.Column("id",             sa.Integer(),  primary_key=True, autoincrement=True),
            sa.Column("session_id",     sa.String(),   sa.ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False),
            sa.Column("role",           sa.String(10), nullable=False),
            sa.Column("text",           sa.Text(),     nullable=False),
            sa.Column("created_at",     sa.DateTime(), nullable=False),
            sa.Column("source",         sa.String(10), nullable=True),
            sa.Column("stt_provenance", sa.Text(),     nullable=True),
            sa.Column("stt_latency_ms", sa.Integer(),  nullable=True),
            sa.CheckConstraint(
                "role IN ('user', 'bot', 'system')",
                name="ck_messages_role",
            ),
        )
        op.create_index("ix_messages_session_id",      "messages", ["session_id"])
        op.create_index("ix_messages_session_created", "messages", ["session_id", "created_at"])


# ── downgrade ─────────────────────────────────────────────────────────────────

def downgrade() -> None:
    # Drop indexes and messages table (safe)
    op.drop_index("ix_messages_session_created", table_name="messages")
    op.drop_index("ix_messages_session_id",      table_name="messages")
    op.drop_table("messages")
    # Note: removing added columns from sessions requires a full table recreate in SQLite.
    # Downgrade leaves the sessions table in its upgraded form to avoid data loss.
