"""Enfileirar indexação de memória longa (Celery); mantém o orquestrador fino."""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

from orion_mcp.core.config.settings import Settings
from orion_mcp.core.state.models import State

_logger = logging.getLogger(__name__)

_MAX_USER = 4000
_MAX_REPLY = 2000


def build_memory_index_content(user_input: str, assistant_text: str | None) -> str:
    u = (user_input or "").strip()[:_MAX_USER]
    if not assistant_text:
        return u
    r = (assistant_text or "").strip()[:_MAX_REPLY]
    if not r:
        return u
    return f"{u}\n\n[resposta]\n{r}"


def build_memory_index_metadata(state: State) -> dict[str, Any]:
    meta: dict[str, Any] = {"intent": state.intent, "source": "chat_turn"}
    if state.current_metric:
        meta["metric"] = state.current_metric
    quoted = (state.entities or {}).get("quoted") if state.entities else None
    if isinstance(quoted, list) and quoted:
        meta["entity"] = str(quoted[0])
    return meta


def enqueue_memory_embed(*, session_id: str, content: str, metadata: dict[str, Any]) -> None:
    if not (content or "").strip():
        return
    try:
        from orion_mcp.infra.queue.celery_app import embed_memory_task
    except Exception:
        _logger.warning("memory_index_queue_import_failed", exc_info=True)
        return
    try:
        embed_memory_task.delay(session_id=session_id, content=content, metadata=metadata)
    except Exception:
        _logger.warning("memory_index_enqueue_failed", exc_info=True)


def maybe_enqueue_memory_index_after_chat(
    *,
    settings: Settings,
    pool: asyncpg.Pool | None,
    session_id: str,
    state: State,
    user_input: str,
    assistant_text: str | None,
) -> None:
    if not settings.enable_long_memory or not settings.enable_memory_index_worker:
        return
    if pool is None:
        return
    content = build_memory_index_content(user_input, assistant_text)
    if not content.strip():
        return
    meta = build_memory_index_metadata(state)
    enqueue_memory_embed(session_id=session_id, content=content, metadata=meta)
