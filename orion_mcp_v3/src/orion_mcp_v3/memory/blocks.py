"""
Conversão memória → :class:`~orion_mcp_v3.contracts.context_block.ContextBlock` (Fase 2.2).
"""

from __future__ import annotations

from collections.abc import Sequence

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.memory.repositories.conversation_state import ConversationMessage

_ROLE_MAP: dict[str, ContextRole] = {
    "system": ContextRole.SYSTEM,
    "user": ContextRole.USER,
    "assistant": ContextRole.ASSISTANT,
    "tool": ContextRole.TOOL,
}


def message_to_context_block(msg: ConversationMessage, *, relevance_score: float = 0.0) -> ContextBlock:
    """Uma mensagem do repositório passa a ser um bloco formal (origem ``MEMORY``)."""
    role = _ROLE_MAP.get(msg.role, ContextRole.NEUTRAL)
    return ContextBlock(
        text=msg.content,
        role=role,
        source=ContextSource.MEMORY,
        block_id=f"msg:{msg.message_id}",
        metadata={"conversation_role": msg.role},
        relevance_score=relevance_score,
    )


def messages_to_context_blocks(messages: Sequence[ConversationMessage]) -> list[ContextBlock]:
    """
    Ordem preservada; relevância cresce com mensagens mais recentes (heurística simples).
    """
    n = len(messages)
    out: list[ContextBlock] = []
    for i, m in enumerate(messages):
        score = (i + 1) / max(1, n)
        out.append(message_to_context_block(m, relevance_score=score))
    return out
