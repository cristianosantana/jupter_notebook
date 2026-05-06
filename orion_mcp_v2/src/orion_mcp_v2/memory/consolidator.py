from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Any

import asyncpg

from orion_mcp_v2.cache.redis_memory import MemoryRedisStore
from orion_mcp_v2.config.settings import Settings, get_settings
from orion_mcp_v2.core.decision.engine import retention_cutoff
from orion_mcp_v2.db.postgres.pool import close_pool, create_pool
from orion_mcp_v2.llm_provider.openai_provider import OpenAIChatService
from orion_mcp_v2.memory.categorizer import categorize_conversation_text
from orion_mcp_v2.memory.memory_builder import build_memory_curta
from orion_mcp_v2.memory.summarizer import summarize_sessions_block
from orion_mcp_v2.skill.loader import load_all_skills
from orion_mcp_v2.state.repository import StateRepository

_logger = logging.getLogger(__name__)


def _extract_user_lines(messages_raw: Any) -> str:
    if not isinstance(messages_raw, list):
        return ""
    lines: list[str] = []
    for item in messages_raw:
        if isinstance(item, dict) and item.get("role") == "user":
            c = item.get("content")
            if isinstance(c, str) and c.strip():
                lines.append(c.strip())
    return "\n".join(lines)


async def consolidate_user_memory(
    user_id: str,
    *,
    settings: Settings | None = None,
    pool: asyncpg.Pool | None = None,
    redis_memory: MemoryRedisStore | None = None,
) -> dict[str, Any]:
    """Job noturno: categoriza sessões, consolida por intent, grava Redis + analytics + cleanup."""
    cfg = settings or get_settings()
    own_pool = pool is None
    pg = pool or await create_pool(cfg)
    if pg is None:
        raise RuntimeError("PostgreSQL não disponível para consolidação")

    repo = StateRepository(pg)
    skills = load_all_skills()
    llm = OpenAIChatService(cfg)

    redis_url = cfg.redis_url
    redis_client = None
    if redis_url and redis_memory is None:
        import redis.asyncio as redis_async

        redis_client = redis_async.from_url(redis_url, decode_responses=True)
        mem_store = MemoryRedisStore(redis_client, ttl_seconds=cfg.memory_curta_ttl_seconds)
    else:
        mem_store = redis_memory or MemoryRedisStore(None, ttl_seconds=cfg.memory_curta_ttl_seconds)

    since = retention_cutoff(days=cfg.session_retention_days)
    sessions = await repo.list_sessions_for_user(user_id, since=since)

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in sessions:
        conv = _extract_user_lines(row.get("messages"))
        if not conv.strip():
            continue
        intent = await categorize_conversation_text(conv, skills, llm)
        groups[intent.value].append(dict(row))

    job_summary: dict[str, Any] = {"user_id": user_id, "categories": [], "sessions_seen": len(sessions)}

    async with pg.acquire() as conn:
        for cat, sess_list in groups.items():
            payload = json.dumps(sess_list, default=str)[:140000]
            body = await summarize_sessions_block(payload, skills, llm)
            mc = build_memory_curta(
                user_id=user_id,
                category=cat,
                consolidated_body=body,
                last_query_hint={"sessions": len(sess_list)},
            )
            await mem_store.set_category(user_id, cat, mc.model_dump(mode="json"))
            await conn.execute(
                """
                INSERT INTO memory_curta_analytics (user_id, category, summary, consolidated_at, ttl_expires_at)
                VALUES ($1, $2, $3::jsonb, NOW(), NOW() + ($4::bigint * interval '1 second'))
                ON CONFLICT (user_id, category) DO UPDATE SET
                  summary = EXCLUDED.summary,
                  consolidated_at = EXCLUDED.consolidated_at,
                  ttl_expires_at = EXCLUDED.ttl_expires_at
                """,
                user_id,
                cat,
                json.dumps(mc.model_dump(mode="json")),
                int(cfg.memory_curta_ttl_seconds),
            )
            job_summary["categories"].append(cat)

    cutoff = retention_cutoff(days=cfg.session_retention_days)
    deleted = await repo.delete_sessions_before(user_id, cutoff)
    job_summary["sessions_deleted"] = deleted

    async with pg.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO memory_consolidation_log (user_id, job_id, status, sessions_processed, consolidated_at)
            VALUES ($1, $2, 'success', $3, NOW())
            """,
            user_id,
            "inline",
            len(sessions),
        )

    if redis_client is not None:
        await redis_client.aclose()
    if own_pool and pg is not None:
        await close_pool(pg)

    _logger.info("consolidation_ok", extra=job_summary)
    return job_summary
