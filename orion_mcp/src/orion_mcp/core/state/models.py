from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class DataCacheEntry(BaseModel):
    summary: str = ""
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class State(BaseModel):
    intent: str = ""
    entities: dict[str, Any] = Field(default_factory=dict)
    current_metric: str = ""
    filters: dict[str, Any] = Field(default_factory=dict)
    data_cache: dict[str, DataCacheEntry] = Field(default_factory=dict)
    insights: list[str] = Field(default_factory=list)
    short_memory: str = ""
    long_memory_refs: list[str] = Field(default_factory=list)
    flags: dict[str, Any] = Field(default_factory=dict)
    datasets: dict[str, Any] = Field(default_factory=dict)
    last_dataset_id: str = ""
    last_query_signature: str = ""

    def model_dump_json_safe(self) -> dict[str, Any]:
        d = self.model_dump(mode="json")
        return d
