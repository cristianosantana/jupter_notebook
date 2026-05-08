"""
Recuperação episódica — turnos recentes como ``ContextBlock`` (ORDEM_IMPLEMENTAÇÃO §8).
"""

from __future__ import annotations

from orion_mcp_v3.contracts.context_block import ContextBlock
from orion_mcp_v3.memory.blocks import messages_to_context_blocks
from orion_mcp_v3.memory.repositories.conversation_state import ConversationStateRepository


class EpisodicRetriever:
    """Envolve o repositório de conversa: mensagens recentes → blocos formais com origem MEMORY."""

    def __init__(self, repository: ConversationStateRepository) -> None:
        self._repo = repository

    def retrieve(self, session_id: str, *, limit: int = 50) -> list[ContextBlock]:
        msgs = self._repo.get_recent(session_id, limit=limit)
        return messages_to_context_blocks(msgs)
