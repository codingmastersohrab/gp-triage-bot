from __future__ import annotations

import io
import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()  # loads .env from the project root if present
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, Form, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.audit import AuditLogger
from app.dialogue import handle_user_text, next_bot_message
from app.models import TriageChecksheet
from app.store import SQLiteSessionStore
from app.summary import generate_summary_text, generate_triage_summary

app = FastAPI(title="GP Triage Bot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store = SQLiteSessionStore()
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

    # Decide next bot message (may set route_outcome / summary_presented as side-effects)
    bot_message = next_bot_message(session)

    # Persist any state changes made inside next_bot_message (route, summary_presented, etc.)
    store.update(session)

    # Persist conversation turn to messages table
    store.add_message(session_id=session_id, role="user", text=user_text)
    store.add_message(session_id=session_id, role="bot",  text=bot_message)

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


@app.post("/audio")
async def transcribe_audio(
    file: UploadFile = File(...),
    session_id: str | None = Form(None),
) -> dict:
    """
    Transcribe uploaded audio with OpenAI Whisper.
    Returns { "text": "<transcript>", "provenance": "stt:openai_whisper" }.
    Raw audio is never written to disk permanently.
    Only metadata is logged to audit.
    """
    try:
        import openai as _openai
    except ImportError:
        raise HTTPException(status_code=500, detail="openai package not installed — run: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured on server")

    content = await file.read()
    file_size = len(content)
    content_type = file.content_type or "audio/webm"
    extension = os.path.splitext(file.filename or "")[1] or ".webm"
    filename = f"recording{extension}"

    # Audit events go to the session log if provided, or a shared fallback file
    audit_session = session_id if session_id else "_audio"

    transcript: str | None = None
    success = False
    error_msg: str | None = None

    t0 = time.monotonic()
    try:
        client = _openai.OpenAI(api_key=api_key)
        result = client.audio.transcriptions.create(
            model="whisper-1",
            file=(filename, io.BytesIO(content), content_type),
        )
        transcript = result.text
        success = True
    except Exception as exc:
        error_msg = str(exc)[:300]
    finally:
        latency_ms = int((time.monotonic() - t0) * 1000)

    audit.log_event(
        session_id=audit_session,
        event_type="audio_transcribed",
        payload={
            "engine": "openai_whisper",
            "content_type": content_type,
            "extension": extension,
            "file_size_bytes": file_size,
            "transcript_char_count": len(transcript) if transcript else 0,
            "latency_ms": latency_ms,
            "success": success,
            "error_message": error_msg,
        },
    )

    if not success:
        raise HTTPException(status_code=502, detail=f"Transcription failed: {error_msg}")

    return {"text": transcript, "provenance": "stt:openai_whisper"}


# Legacy placeholder — kept so existing callers don't get a 404

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

    content = await file.read()

    audit.log_event(
        session_id=session_id,
        event_type="audio_received",
        payload={
            "filename": file.filename,
            "content_type": file.content_type,
            "num_bytes": len(content),
            "note": "legacy endpoint — use POST /audio for STT",
        },
    )

    return AudioInputResponse(
        transcript=None,
        bot_message=(
            "Please use the voice button in the web interface, "
            "or POST to /audio directly."
        ),
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
