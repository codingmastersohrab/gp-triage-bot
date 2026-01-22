from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field


class InputMode(str, Enum):
    VOICE = "voice"
    TEXT = "text"


class DurationUnit(str, Enum):
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"


class Duration(BaseModel):
    value: int = Field(ge=0)
    unit: DurationUnit


class TriageChecksheet(BaseModel):
    session_id: str
    created_at: datetime

    main_issue: Optional[str] = None
    symptom_description_raw: Optional[str] = None
    duration: Optional[Duration] = None
    severity_0_10: Optional[int] = Field(default=None, ge=0, le=10)

    red_flags: Dict[str, Optional[bool]] = Field(default_factory=dict)

    confirmed: Dict[str, bool] = Field(default_factory=dict)
    provenance: Dict[str, InputMode] = Field(default_factory=dict)
    confidence: Dict[str, float] = Field(default_factory=dict)

    route_outcome: Optional[str] = None
    route_rationale: Optional[str] = None
