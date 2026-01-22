from __future__ import annotations

import re
from typing import Optional, Tuple

from app.models import Duration, DurationUnit


_WORD_TO_NUM = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
}


def parse_duration(text: str) -> Optional[Duration]:
    """
    Very small MVP duration parser.
    Handles: "3 days", "2 weeks", "one week", "a week", "an hour".
    If unclear, returns None.
    """
    t = text.strip().lower()

    # common "a/an"
    t = t.replace("a ", "1 ").replace("an ", "1 ")

    # replace word numbers (one, two, ...)
    for w, n in _WORD_TO_NUM.items():
        t = re.sub(rf"\b{w}\b", str(n), t)

    # match "<num> <unit>"
    m = re.search(r"\b(\d+)\s*(hour|hours|day|days|week|weeks|month|months)\b", t)
    if not m:
        return None

    value = int(m.group(1))
    unit_raw = m.group(2)

    if unit_raw.startswith("hour"):
        unit = DurationUnit.HOURS
    elif unit_raw.startswith("day"):
        unit = DurationUnit.DAYS
    elif unit_raw.startswith("week"):
        unit = DurationUnit.WEEKS
    else:
        unit = DurationUnit.MONTHS

    return Duration(value=value, unit=unit)

def parse_severity_0_10(text: str) -> Optional[int]:
    """
    Parse severity from 0-10.
    Handles: '8', '8/10', '8 out of 10', 'ten', '0'.
    Returns int 0..10 or None.
    """
    t = text.strip().lower()

    # normalise word numbers
    for w, n in _WORD_TO_NUM.items():
        t = re.sub(rf"\b{w}\b", str(n), t)

    # common patterns
    m = re.search(r"\b(\d{1,2})\b", t)
    if not m:
        return None

    val = int(m.group(1))
    if 0 <= val <= 10:
        return val
    return None
