"""
Session Manager (Fase 6.2) — gestão de sessões de conversa com estado cognitivo.

Mantém ``conversation_id``, ``memory_window`` (mensagens recentes como blocos),
``runtime_state`` (:class:`~ContextState`) e repositório de memória por sessão.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from orion_mcp_v3.config.settings import get_settings
from orion_mcp_v3.memory.repositories.conversation_state import (
    ConversationMessage,
    ConversationStateRepository,
    InMemoryConversationStateRepository,
)
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy
from orion_mcp_v3.runtime.context_state import CognitivePhase, ContextState

_LOG = logging.getLogger(__name__)


def _message_to_stored_dict(msg: ConversationMessage) -> dict[str, Any]:
    return {
        "role": msg.role,
        "content": msg.content,
        "created_at": msg.created_at.isoformat(),
        "message_id": msg.message_id,
    }


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
    por qualquer implementação de :class:`~ConversationStateRepository`.

    Se ``shared_conversation_repository_slot`` for um dict partilhado com a app
    (ex.: estado do lifespan), a chave ``conversation_repository`` sobrepõe o
    repositório em memória quando presente (ex.: Postgres após arranque do pool).
    """

    _CONVERSATION_REPO_KEY = "conversation_repository"
    _EMBEDDING_STORE_KEY = "chat_turn_embedding_store"

    def __init__(
        self,
        *,
        repository: ConversationStateRepository | None = None,
        shared_conversation_repository_slot: dict[str, Any] | None = None,
        default_token_budget: int = 4096,
        default_policy: AttentionPolicy = AttentionPolicy.ANALYTICAL,
        memory_window: int = 60,
        session_list_max_messages: int | None = None,
    ) -> None:
        self._explicit_repository = repository
        self._shared_slot = shared_conversation_repository_slot
        self._fallback = InMemoryConversationStateRepository()
        self._sessions: dict[str, Session] = {}
        self._default_budget = default_token_budget
        self._default_policy = default_policy
        self._memory_window = memory_window
        self._session_list_max_messages = session_list_max_messages
        self._embedding_store_warned = False

    def _session_list_limit(self) -> int:
        if self._session_list_max_messages is not None:
            return self._session_list_max_messages
        return get_settings().session_list_max_messages

    def _active_repo(self) -> ConversationStateRepository:
        if self._shared_slot is not None:
            r = self._shared_slot.get(self._CONVERSATION_REPO_KEY)
            if r is not None:
                return r  # type: ignore[return-value]
        return self._explicit_repository or self._fallback

    @property
    def repository(self) -> ConversationStateRepository:
        return self._active_repo()

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

    def _embedding_store(self) -> Any | None:
        if self._shared_slot is None:
            return None
        return self._shared_slot.get(self._EMBEDDING_STORE_KEY)

    async def _index_turn_embedding(self, session_id: str, msg: ConversationMessage) -> None:
        if not get_settings().embedding_should_index:
            return
        store = self._embedding_store()
        if store is None:
            settings = get_settings()
            if settings.embedding_should_index and not self._embedding_store_warned:
                self._embedding_store_warned = True
                _LOG.warning(
                    "ORION_EMBEDDING_ENABLED=true mas chat_turn_embedding_store não está "
                    "no lifespan (Postgres/pgvector/migrações ou falha no arranque)"
                )
            return
        try:
            await store.index_turn(session_id, msg)
        except Exception:
            _LOG.exception(
                "Falha ao indexar embedding (session=%s message_id=%s)",
                session_id,
                msg.message_id,
            )

    async def record_user_message(self, session: Session, content: str) -> ConversationMessage:
        """Grava mensagem do utilizador e incrementa turno."""
        msg = await self._active_repo().append_message(session.conversation_id, "user", content)
        session.turn_count += 1
        session.state.cognitive_phase = CognitivePhase.RETRIEVING
        await self._index_turn_embedding(session.conversation_id, msg)
        return msg

    async def record_assistant_message(self, session: Session, content: str) -> ConversationMessage:
        """Grava resposta do assistente."""
        msg = await self._active_repo().append_message(session.conversation_id, "assistant", content)
        session.state.cognitive_phase = CognitivePhase.IDLE
        await self._index_turn_embedding(session.conversation_id, msg)
        return msg

    async def get_recent_messages(self, session: Session) -> list[ConversationMessage]:
        """Mensagens recentes dentro da memory_window."""
        return await self._active_repo().get_recent(session.conversation_id, limit=self._memory_window)

    async def list_session_summaries(self) -> list[dict[str, Any]]:
        """Identificadores conhecidos + mensagens completas no formato persistido (JSON/DB)."""
        repo_ids: list[str] = []
        list_fn = getattr(self._active_repo(), "list_session_ids", None)
        if callable(list_fn):
            repo_ids = await list_fn()
        seen = set(self._sessions.keys()) | set(repo_ids)

        async def preview_ts(cid: str) -> tuple[str, str]:
            msgs = await self._active_repo().get_recent(cid, limit=1)
            if not msgs:
                return ("", cid)
            return (msgs[-1].created_at.isoformat(), cid)

        keys_with_ts = await asyncio.gather(*[preview_ts(c) for c in seen])
        ordered = [cid for _, cid in sorted(keys_with_ts, key=lambda t: t[0], reverse=True)]

        out: list[dict[str, Any]] = []
        for cid in ordered:
            sess = self._sessions.get(cid)
            turn = sess.turn_count if sess else 0
            recent = await self._active_repo().get_recent(cid, limit=self._session_list_limit())
            messages = [_message_to_stored_dict(m) for m in recent]
            out.append({"conversation_id": cid, "turn_count": turn, "messages": messages})
        return out

    def update_phase(self, session: Session, phase: CognitivePhase) -> None:
        session.state.cognitive_phase = phase

    def list_sessions(self) -> list[str]:
        return list(self._sessions.keys())
