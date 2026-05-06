from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str
    ts: datetime | None = None


class ConversationStateV2(BaseModel):
    session_id: str
    user_id: str
    messages: list[Message] = Field(default_factory=list)
    last_data: dict[str, Any] | None = None
    last_query_signature: str | None = None
    state_status: str = "active"
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def append_exchange(self, user_text: str, assistant_text: str) -> None:
        now = datetime.now(timezone.utc)
        self.messages.append(Message(role="user", content=user_text, ts=now))
        self.messages.append(Message(role="assistant", content=assistant_text, ts=now))
