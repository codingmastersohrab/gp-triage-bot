from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any, Dict, Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from app.models import TriageChecksheet


_Base = declarative_base()
_DB_PATH = Path(__file__).resolve().parent.parent / "gp_triage.db"
_SCHEMA_VERSION = 1


# ORM row definitions

class _SessionRow(_Base):
    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'completed', 'abandoned')",
            name="ck_sessions_status",
        ),
    )

    session_id        = Column(String,     primary_key=True)
    data              = Column(Text,       nullable=False)
    created_at        = Column(DateTime,   nullable=True)
    updated_at        = Column(DateTime,   nullable=True)
    status            = Column(String(20), nullable=False, default="active",           server_default="active")
    schema_version    = Column(Integer,    nullable=False, default=_SCHEMA_VERSION,    server_default=str(_SCHEMA_VERSION))

    # Structured queryable fields (derived from session JSON on every write)
    symptom_category      = Column(Text,    nullable=True)
    main_issue            = Column(Text,    nullable=True)
    duration_value        = Column(Integer, nullable=True)
    duration_unit         = Column(Text,    nullable=True)
    severity_score        = Column(Text,    nullable=True)
    red_flags_list        = Column(Text,    nullable=True)   # JSON of pathway_answers
    completed_at          = Column(DateTime, nullable=True)
    pathway_name          = Column(Text,    nullable=True)
    pathway_version       = Column(Integer, nullable=True)
    number_of_turns       = Column(Integer, nullable=True)

    # From migration 001 (kept)
    routing_outcome       = Column(Text,    nullable=True)
    routing_rationale     = Column(Text,    nullable=True)
    red_flags_present     = Column(Integer, nullable=True)   # 1/0/NULL
    summary_text_snapshot = Column(Text,    nullable=True)


class _MessageRow(_Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'bot', 'system')",
            name="ck_messages_role",
        ),
        Index("ix_messages_session_id", "session_id"),
        Index("ix_messages_session_created", "session_id", "created_at"),
    )

    id             = Column(Integer,    primary_key=True, autoincrement=True)
    session_id     = Column(String,     ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False)
    role           = Column(String(10), nullable=False)
    text           = Column(Text,       nullable=False)
    created_at     = Column(DateTime,   nullable=False)
    source         = Column(String(10), nullable=True)
    stt_provenance = Column(Text,       nullable=True)
    stt_latency_ms = Column(Integer,    nullable=True)


# SQLite pragmas for reliability (WAL mode, foreign keys, busy timeout)

def _apply_pragmas(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# Field extraction helpers

def _red_flags_present(session: TriageChecksheet) -> Optional[int]:
    answers = session.pathway_answers or session.red_flags
    if not answers:
        return None
    if any(v is True for v in answers.values()):
        return 1
    if all(v is not None for v in answers.values()):
        return 0
    return None


def _status_for(session: TriageChecksheet) -> str:
    if session.route_outcome in ("EMERGENCY_NOW", "URGENT_SAME_DAY", "ROUTINE_GP"):
        if session.summary_confirmed is True:
            return "completed"
    return "active"


def _structured_fields(session: TriageChecksheet, now: datetime) -> Dict[str, Any]:
    answers = session.pathway_answers
    return {
        "symptom_category":   session.symptom_category,
        "main_issue":         session.main_issue,
        "duration_value":     session.duration.value if session.duration else None,
        "duration_unit":      session.duration.unit.value if session.duration else None,
        "severity_score":     str(session.severity_0_10) if session.severity_0_10 is not None else None,
        "red_flags_list":     json.dumps(answers) if answers else None,
        "pathway_name":       session.pathway_name,
        "pathway_version":    session.pathway_version,
        "number_of_turns":    session.number_of_turns,
        "routing_outcome":    session.route_outcome,
        "routing_rationale":  session.route_rationale,
        "red_flags_present":  _red_flags_present(session),
        "completed_at":       now if _status_for(session) == "completed" else None,
    }


# SQLite-backed session store

class SQLiteSessionStore:
    def __init__(self, db_path: Path = _DB_PATH) -> None:
        engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False},
        )
        event.listen(engine, "connect", _apply_pragmas)
        _Base.metadata.create_all(engine)
        self._Session = sessionmaker(bind=engine)

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    def put(self, session: TriageChecksheet) -> None:
        now    = self._now()
        fields = _structured_fields(session, now)
        with self._Session() as db:
            db.add(_SessionRow(
                session_id=session.session_id,
                data=session.model_dump_json(),
                created_at=now,
                updated_at=now,
                status="active",
                schema_version=_SCHEMA_VERSION,
                **fields,
            ))
            db.commit()

    def get(self, session_id: str) -> Optional[TriageChecksheet]:
        with self._Session() as db:
            row = db.get(_SessionRow, session_id)
            if row is None:
                return None
            return TriageChecksheet.model_validate_json(row.data)

    def update(self, session: TriageChecksheet) -> None:
        now    = self._now()
        fields = _structured_fields(session, now)
        status = _status_for(session)
        with self._Session() as db:
            row = db.get(_SessionRow, session.session_id)
            if row is None:
                db.add(_SessionRow(
                    session_id=session.session_id,
                    data=session.model_dump_json(),
                    created_at=now,
                    updated_at=now,
                    status=status,
                    schema_version=_SCHEMA_VERSION,
                    **fields,
                ))
            else:
                row.data       = session.model_dump_json()
                row.updated_at = now
                row.status     = status
                for k, v in fields.items():
                    setattr(row, k, v)
            db.commit()

    def add_message(
        self,
        session_id: str,
        role: str,
        text: str,
        source: Optional[str] = None,
        stt_provenance: Optional[str] = None,
        stt_latency_ms: Optional[int] = None,
    ) -> None:
        with self._Session() as db:
            db.add(_MessageRow(
                session_id=session_id,
                role=role,
                text=text,
                created_at=self._now(),
                source=source,
                stt_provenance=stt_provenance,
                stt_latency_ms=stt_latency_ms,
            ))
            db.commit()


# In-memory store (kept for testing and reference)

class InMemorySessionStore:
    def __init__(self) -> None:
        self._lock = Lock()
        self._sessions: Dict[str, TriageChecksheet] = {}

    def put(self, session: TriageChecksheet) -> None:
        with self._lock:
            self._sessions[session.session_id] = session

    def get(self, session_id: str) -> Optional[TriageChecksheet]:
        with self._lock:
            return self._sessions.get(session_id)

    def update(self, session: TriageChecksheet) -> None:
        with self._lock:
            self._sessions[session.session_id] = session
