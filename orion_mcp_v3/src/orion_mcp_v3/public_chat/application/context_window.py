"""Janela de contexto consultiva via cadeia ancestral."""

from __future__ import annotations

import time
from uuid import UUID

from orion_mcp_v3.public_chat.domain.models import AncestorTurn
from orion_mcp_v3.public_chat.infrastructure.pipeline_trace import log_public_chat_event
from orion_mcp_v3.public_chat.infrastructure.response_store import ResponseStore


async def load_context_window(
    store: ResponseStore,
    parent_question_id: UUID | None,
    *,
    max_depth: int = 3,
) -> list[AncestorTurn]:
    """Carrega ancestrais anteriores ao pai imediato, truncando em ``max_depth``."""
    t0 = time.monotonic()
    log_public_chat_event(
        etapa="context_window.load",
        fase="pre",
        dados={
            "parent_question_id": str(parent_question_id) if parent_question_id else None,
            "max_depth": max_depth,
        },
    )
    if parent_question_id is None or max_depth <= 0:
        log_public_chat_event(
            etapa="context_window.load",
            fase="post",
            dados={"latency_ms": round((time.monotonic() - t0) * 1000.0, 2), "ancestor_count": 0},
        )
        return []
    parent = await store.get_question(parent_question_id)
    if parent is None or parent.parent_question_id is None:
        log_public_chat_event(
            etapa="context_window.load",
            fase="post",
            dados={
                "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
                "ancestor_count": 0,
                "parent_found": parent is not None,
            },
        )
        return []
    ancestors = await store.load_ancestor_chain(parent.parent_question_id, max_depth)
    log_public_chat_event(
        etapa="context_window.load",
        fase="post",
        dados={
            "latency_ms": round((time.monotonic() - t0) * 1000.0, 2),
            "ancestor_count": len(ancestors),
        },
    )
    return ancestors
