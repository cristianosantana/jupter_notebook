"""
Estado de conversa — protocolo async (memória ou PostgreSQL).

CRUD mínimo: ``append_message`` / ``get_recent`` / ``list_session_ids``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    """Mensagem literal guardada no repositório."""

    session_id: str
    role: str
    content: str
    message_id: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@runtime_checkable
class ConversationStateRepository(Protocol):
    async def append_message(self, session_id: str, role: str, content: str) -> ConversationMessage: ...

    async def get_recent(self, session_id: str, limit: int = 50) -> list[ConversationMessage]: ...

    async def list_session_ids(self) -> list[str]: ...


class InMemoryConversationStateRepository:
    """Armazenamento por ``session_id`` em listas ordenadas (MVP)."""

    def __init__(self) -> None:
        self._messages: dict[str, list[ConversationMessage]] = {}
        self._seq: dict[str, int] = {}

    async def append_message(self, session_id: str, role: str, content: str) -> ConversationMessage:
        sid = session_id.strip() or "default"
        n = self._seq.get(sid, 0) + 1
        self._seq[sid] = n
        msg = ConversationMessage(session_id=sid, role=role.strip().lower(), content=content, message_id=n)
        self._messages.setdefault(sid, []).append(msg)
        return msg

    async def get_recent(self, session_id: str, limit: int = 50) -> list[ConversationMessage]:
        sid = session_id.strip() or "default"
        items = self._messages.get(sid, [])
        if limit <= 0:
            return []
        return items[-limit:]

    async def list_session_ids(self) -> list[str]:
        """Todos os ``session_id`` que já receberam mensagens (in-memory)."""
        return sorted(self._messages.keys())
