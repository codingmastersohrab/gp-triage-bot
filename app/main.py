from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.dialogue import handle_user_text, next_bot_message
from app.models import TriageChecksheet
from app.store import InMemorySessionStore

app = FastAPI(title="GP Triage Bot API")
store = InMemorySessionStore()


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

    handle_user_text(session, req.text)
    store.update(session)

    bot_message = next_bot_message(session)
    return UserInputResponse(bot_message=bot_message, session=session)
