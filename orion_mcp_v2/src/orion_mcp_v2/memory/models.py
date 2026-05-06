from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class MemoryCurta(BaseModel):
    user_id: str
    category: str
    consolidated_at: datetime
    summary: str
    key_metrics: dict[str, Any] = Field(default_factory=dict)
    recent_questions: list[str] = Field(default_factory=list)
    last_results: dict[str, Any] | None = None
