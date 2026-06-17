"""Janela de contexto consultiva via cadeia ancestral."""

from __future__ import annotations

from uuid import UUID

from orion_mcp_v3.public_chat.domain.models import AncestorTurn
from orion_mcp_v3.public_chat.infrastructure.response_store import ResponseStore


async def load_context_window(
    store: ResponseStore,
    parent_question_id: UUID | None,
    *,
    max_depth: int = 3,
) -> list[AncestorTurn]:
    """Carrega ancestrais anteriores ao pai imediato, truncando em ``max_depth``."""
    if parent_question_id is None or max_depth <= 0:
        return []
    parent = await store.get_question(parent_question_id)
    if parent is None or parent.parent_question_id is None:
        return []
    return await store.load_ancestor_chain(parent.parent_question_id, max_depth)
