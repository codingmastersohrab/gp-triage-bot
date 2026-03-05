from __future__ import annotations

import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, UploadFile, File
from pydantic import BaseModel

from app.audit import AuditLogger
from app.dialogue import handle_user_text, next_bot_message
from app.models import TriageChecksheet
from app.store import InMemorySessionStore
from app.summary import generate_summary_text, generate_triage_summary

app = FastAPI(title="GP Triage Bot API")
store = InMemorySessionStore()
audit = AuditLogger(log_dir=Path("logs"))


@app.get("/hello")
def hello():
    return {"message": "Hello! Your API is running."}


class StartSessionResponse(BaseModel):
    session: TriageChecksheet


@app.post("/session/start", response_model=StartSessionResponse)
def start_session() -> StartSessionResponse:
    session = TriageChecksheet(
        session_id=str(uuid4()),
        created_at=datetime.now(timezone.utc),
    )
    store.put(session)

    audit.log_event(
        session_id=session.session_id,
        event_type="session_started",
        payload={"session": session.model_dump()},
    )

    return StartSessionResponse(session=session)


class UserInputRequest(BaseModel):
    text: str


class UserInputResponse(BaseModel):
    bot_message: str
    session: TriageChecksheet


@app.post("/session/{session_id}/user_input", response_model=UserInputResponse)
def user_input(session_id: str, req: UserInputRequest) -> UserInputResponse:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    before = session.model_dump()
    user_text = req.text

    # Apply user input -> update checksheet
    handle_user_text(session, user_text)
    store.update(session)

    # Decide next bot message
    bot_message = next_bot_message(session)

    after = session.model_dump()

    audit.log_event(
        session_id=session_id,
        event_type="turn",
        payload={
            "user_text": user_text,
            "before": before,
            "after": after,
            "bot_message": bot_message,
        },
    )

    return UserInputResponse(bot_message=bot_message, session=session)


class AudioInputResponse(BaseModel):
    transcript: str | None
    bot_message: str
    session: TriageChecksheet
    used_fallback: bool


@app.post("/session/{session_id}/audio", response_model=AudioInputResponse)
async def audio_input(session_id: str, file: UploadFile = File(...)) -> AudioInputResponse:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    # Save upload to a temp file
    suffix = os.path.splitext(file.filename or "")[1] or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        temp_path = tmp.name
        content = await file.read()
        tmp.write(content)

    # Log audio received (metadata only)
    audit.log_event(
        session_id=session_id,
        event_type="audio_received",
        payload={
            "filename": file.filename,
            "content_type": file.content_type,
            "num_bytes": len(content),
            "temp_path": temp_path,
        },
    )

    # MVP skeleton: no STT yet (forces safe text fallback)
    transcript = None
    bot_message = (
        "Sorry — I couldn’t transcribe that audio yet (STT not enabled). "
        "Please type your message instead using /session/{session_id}/user_input."
    )

    audit.log_event(
        session_id=session_id,
        event_type="audio_transcription_failed",
        payload={"reason": "stt_not_implemented"},
    )

    return AudioInputResponse(
        transcript=transcript,
        bot_message=bot_message,
        session=session,
        used_fallback=True,
    )


class SummaryResponse(BaseModel):
    summary_text: str
    summary_structured: dict
    session: TriageChecksheet


@app.get("/session/{session_id}/summary", response_model=SummaryResponse)
def get_summary(session_id: str) -> SummaryResponse:
    session = store.get(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session_id")

    summary_text = generate_summary_text(session)
    summary_structured = generate_triage_summary(session)

    audit.log_event(
        session_id=session_id,
        event_type="summary_generated",
        payload={"summary_structured": summary_structured},
    )

    return SummaryResponse(
        summary_text=summary_text,
        summary_structured=summary_structured,
        session=session,
    )
