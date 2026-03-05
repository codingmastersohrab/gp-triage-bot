from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from fastapi.encoders import jsonable_encoder


@dataclass
class AuditLogger:
    log_dir: Path

    def __post_init__(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, session_id: str) -> Path:
        return self.log_dir / f"{session_id}.jsonl"

    def log_event(self, session_id: str, event_type: str, payload: Dict[str, Any]) -> None:
        record = {
            "ts_utc": datetime.now(timezone.utc).isoformat(),
            "session_id": session_id,
            "event_type": event_type,
            "payload": payload,
        }

        # Convert datetimes and other non-JSON-native types safely
        record = jsonable_encoder(record)

        path = self._path_for(session_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
