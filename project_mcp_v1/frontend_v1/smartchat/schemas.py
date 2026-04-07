"""DTOs alinhados à API FastAPI."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass
class ChatMessageUser:
    role: Literal["user"]
    content: str


@dataclass
class ChatMessageAssistant:
    role: Literal["assistant"]
    content: str
    content_blocks: dict[str, Any] | None = None


ChatMessage = ChatMessageUser | ChatMessageAssistant


@dataclass
class SessionRow:
    session_id: str
    user_id: str | None
    current_agent: str
    status: str
    started_at: str | None
    last_active_at: str | None


@dataclass
class ChatResponse:
    reply: str
    tools_used: list[Any]
    agent_used: str
    trace_run_id: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    content_blocks: dict[str, Any] | None = None


@dataclass
class StoredMsg:
    role: str | None = None
    content: Any = None
    name: str | None = None


@dataclass
class SessionDetailResponse:
    session: dict[str, Any]
    messages: list[StoredMsg] = field(default_factory=list)
    trace_run_id: str | None = None
    persistence_enabled: bool = True
