from __future__ import annotations

import asyncio
import logging

from celery import Celery

from orion_mcp.core.config.settings import get_settings

_logger = logging.getLogger(__name__)


def make_celery() -> Celery:
    settings = get_settings()
    app = Celery("orion", broker=settings.celery_broker_url, backend=settings.celery_broker_url)
    app.conf.task_default_queue = "orion"
    return app


celery_app = make_celery()


@celery_app.task(name="orion.embed_memory")
def embed_memory_task(session_id: str, content: str, metadata: dict) -> str:
    """
    Worker: embedding OpenAI + INSERT em memory_embeddings.
    Não bloqueia o pedido HTTP; falhas são engolidas em run_embed_and_insert (log).
    """
    from orion_mcp.core.memory.embed_pipeline import run_embed_and_insert

    async def _run() -> None:
        await run_embed_and_insert(
            session_id=session_id,
            content=content,
            metadata=dict(metadata or {}),
        )

    try:
        asyncio.run(_run())
    except Exception:
        _logger.exception("embed_memory_task_failed")
        return "error"
    return "ok"
