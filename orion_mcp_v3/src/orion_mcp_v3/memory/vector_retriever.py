"""Recuperação semântica via pgvector (``chat_turn_embeddings``)."""

from __future__ import annotations

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.memory.blocks import _ROLE_MAP
from orion_mcp_v3.memory.chat_turn_embedding_store import ChatTurnEmbeddingStore


class VectorRetriever:
    """Produz :class:`~ContextBlock` a partir de busca vectorial por sessão."""

    def __init__(self, store: ChatTurnEmbeddingStore) -> None:
        self._store = store

    async def retrieve(
        self,
        query: str,
        session_id: str,
        *,
        top_k: int = 5,
    ) -> list[ContextBlock]:
        hits = await self._store.search(session_id, query, top_k=top_k)
        blocks: list[ContextBlock] = []
        for message_id, role, content, similarity in hits:
            blocks.append(
                ContextBlock(
                    text=content,
                    role=_ROLE_MAP.get(role.strip().lower(), ContextRole.NEUTRAL),
                    source=ContextSource.MEMORY,
                    block_id=f"vec:{message_id}",
                    metadata={
                        "retrieval": "vector",
                        "vector_similarity": round(similarity, 4),
                        "message_id": message_id,
                        "conversation_role": role,
                    },
                    relevance_score=min(1.0, max(0.55, similarity)),
                )
            )
        return blocks
