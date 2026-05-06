from __future__ import annotations

import asyncio
import logging

from orion_mcp_v2.config.settings import get_settings
from orion_mcp_v2.db.postgres.pool import close_pool, create_pool
from orion_mcp_v2.memory.consolidator import consolidate_user_memory
from orion_mcp_v2.observability.metrics import CONSOLIDATION_SECONDS
from orion_mcp_v2.state.repository import StateRepository
from orion_mcp_v2.tasks.celery_app import celery_app

_logger = logging.getLogger(__name__)


@celery_app.task(name="orion_v2.consolidate_user", bind=True, max_retries=3, default_retry_delay=300)
def consolidate_user_task(self, user_id: str) -> dict:
    import time

    t0 = time.perf_counter()
    try:

        async def _run() -> dict:
            return await consolidate_user_memory(user_id)

        out = asyncio.run(_run())
        CONSOLIDATION_SECONDS.observe(time.perf_counter() - t0)
        return out
    except Exception as exc:
        _logger.exception("consolidate_user_failed", extra={"user_id": user_id})
        raise self.retry(exc=exc) from exc


@celery_app.task(name="orion_v2.consolidate_all_users")
def consolidate_all_users() -> dict:
    async def _list_users() -> list[str]:
        pool = await create_pool(get_settings())
        if pool is None:
            return []
        try:
            repo = StateRepository(pool)
            return await repo.list_distinct_user_ids()
        finally:
            await close_pool(pool)

    users = asyncio.run(_list_users())
    for uid in users:
        consolidate_user_task.delay(uid)
    return {"queued": len(users)}
