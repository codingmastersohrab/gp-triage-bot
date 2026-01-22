from __future__ import annotations

from threading import Lock
from typing import Dict, Optional

from app.models import TriageChecksheet


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
