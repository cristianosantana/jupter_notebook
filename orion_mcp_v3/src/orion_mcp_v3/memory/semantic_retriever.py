"""
Recuperação semântica lexical (MVP) até existir índice vectorial — ORDEM_IMPLEMENTAÇÃO §8.

Pontua mensagens do pool recente por sobreposição de tokens com a *query*.
"""

from __future__ import annotations

import re

from orion_mcp_v3.contracts.context_block import ContextBlock
from orion_mcp_v3.memory.blocks import messages_to_context_blocks
from orion_mcp_v3.memory.repositories.conversation_state import ConversationMessage, ConversationStateRepository


def _tokens(s: str) -> set[str]:
    return {t for t in re.split(r"\W+", s.lower()) if len(t) >= 2}


def _score(query_toks: set[str], text: str) -> float:
    if not query_toks:
        return 0.0
    doc = _tokens(text)
    if not doc:
        return 0.0
    inter = len(query_toks & doc)
    return inter / max(1, len(query_toks))


class SemanticRetriever:
    """
    Escolhe até ``top_k`` mensagens mais alinhadas com a query entre as últimas ``pool_limit``.
    """

    def __init__(self, repository: ConversationStateRepository) -> None:
        self._repo = repository

    def retrieve(
        self,
        query: str,
        session_id: str,
        *,
        pool_limit: int = 80,
        top_k: int = 5,
    ) -> list[ContextBlock]:
        pool = self._repo.get_recent(session_id, limit=pool_limit)
        if not pool or not query.strip():
            return []

        qtok = _tokens(query)
        scored: list[tuple[ConversationMessage, float]] = []
        for m in pool:
            s = _score(qtok, m.content)
            if s > 0:
                scored.append((m, s))
        scored.sort(key=lambda x: -x[1])
        picked = [m for m, _ in scored[: max(1, top_k)]]
        if not picked:
            picked = pool[-min(top_k, len(pool)) :]
        return messages_to_context_blocks(picked)
