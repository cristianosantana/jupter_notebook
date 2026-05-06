from __future__ import annotations

from enum import Enum


class Action(str, Enum):
    CALL_TOOL = "CALL_TOOL"
    GENERATE_RESPONSE = "GENERATE_RESPONSE"
    GENERATE_INSIGHTS = "GENERATE_INSIGHTS"
    FORMAT_RESPONSE = "FORMAT_RESPONSE"
