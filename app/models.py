from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional

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

    # Slot-filled fields
    main_issue: Optional[str] = None
    symptom_description_raw: Optional[str] = None
    duration: Optional[Duration] = None
    severity_0_10: Optional[int] = Field(default=None, ge=0, le=10)

    # Pathway tracking
    symptom_category: Optional[str] = None      # 'headache' | 'chest_pain' | etc.
    pathway_name: Optional[str] = None          # e.g. 'headache_v2'
    pathway_version: int = 2
    pathway_answers: Dict[str, Any] = Field(default_factory=dict)

    # Legacy red_flags field — kept for backward compatibility with old sessions
    red_flags: Dict[str, Optional[bool]] = Field(default_factory=dict)

    # Confirmation and provenance tracking
    confirmed: Dict[str, bool] = Field(default_factory=dict)
    provenance: Dict[str, InputMode] = Field(default_factory=dict)
    confidence: Dict[str, float] = Field(default_factory=dict)

    # Routing
    route_outcome: Optional[str] = None
    route_rationale: Optional[str] = None
    route_decided_at: Optional[datetime] = None

    # End-of-session summary confirmation
    summary_presented: bool = False
    summary_confirmed: Optional[bool] = None
    awaiting_correction_of: Optional[str] = None   # 'issue' | 'duration' | 'severity' | 'asking'

    # Mid-session inline correction
    # Set when user says "I meant X" during pathway questions.
    # Dict keys: 'field' (str), 'value' (parsed value), optionally 'key' (pathway step key).
    mid_correction: Optional[Dict[str, Any]] = None

    # Red-flag answer pending confirmation
    # Set when user answers "yes" to a red-flag step; records step key.
    # The answer is NOT written to pathway_answers until the user confirms.
    pending_red_flag_confirm: Optional[Dict[str, Any]] = None

    # Evaluation metrics
    number_of_turns: int = 0
    number_of_clarifications: int = 0
    stt_used: bool = False
