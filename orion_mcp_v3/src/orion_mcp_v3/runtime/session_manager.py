"""
Session Manager (Fase 6.2) — gestão de sessões de conversa com estado cognitivo.

Mantém ``conversation_id``, ``memory_window`` (mensagens recentes como blocos),
``runtime_state`` (:class:`~ContextState`) e repositório de memória por sessão.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from orion_mcp_v3.contracts.context_block import ContextBlock
from orion_mcp_v3.memory.repositories.conversation_state import (
    ConversationMessage,
    InMemoryConversationStateRepository,
)
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy
from orion_mcp_v3.runtime.context_state import CognitivePhase, ContextState


@dataclass
class Session:
    """Estado de uma sessão activa."""

    conversation_id: str
    state: ContextState = field(default_factory=ContextState)
    turn_count: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


class SessionManager:
    """
    Cria/recupera sessões por ``conversation_id`` e persiste mensagens no repositório.

    Usa :class:`~InMemoryConversationStateRepository` por omissão; substituível
    por qualquer implementação de ``ConversationStateRepository``.
    """

    def __init__(
        self,
        *,
        repository: Any | None = None,
        default_token_budget: int = 4096,
        default_policy: AttentionPolicy = AttentionPolicy.BALANCED,
        memory_window: int = 60,
    ) -> None:
        self._repo = repository or InMemoryConversationStateRepository()
        self._sessions: dict[str, Session] = {}
        self._default_budget = default_token_budget
        self._default_policy = default_policy
        self._memory_window = memory_window

    @property
    def repository(self):
        return self._repo

    @property
    def memory_window(self) -> int:
        return self._memory_window

    def get_or_create(self, conversation_id: str | None = None) -> Session:
        """Obtém sessão existente ou cria nova com UUID."""
        cid = (conversation_id or "").strip()
        if not cid:
            cid = str(uuid.uuid4())
        if cid in self._sessions:
            return self._sessions[cid]
        session = Session(
            conversation_id=cid,
            state=ContextState(
                token_budget=self._default_budget,
                active_policy=self._default_policy,
            ),
        )
        self._sessions[cid] = session
        return session

    def record_user_message(self, session: Session, content: str) -> ConversationMessage:
        """Grava mensagem do utilizador e incrementa turno."""
        msg = self._repo.append_message(session.conversation_id, "user", content)
        session.turn_count += 1
        session.state.cognitive_phase = CognitivePhase.RETRIEVING
        return msg

    def record_assistant_message(self, session: Session, content: str) -> ConversationMessage:
        """Grava resposta do assistente."""
        msg = self._repo.append_message(session.conversation_id, "assistant", content)
        session.state.cognitive_phase = CognitivePhase.IDLE
        return msg

    def get_recent_messages(self, session: Session) -> list[ConversationMessage]:
        """Mensagens recentes dentro da memory_window."""
        return self._repo.get_recent(session.conversation_id, limit=self._memory_window)

    def update_phase(self, session: Session, phase: CognitivePhase) -> None:
        session.state.cognitive_phase = phase

    def list_sessions(self) -> list[str]:
        return list(self._sessions.keys())
