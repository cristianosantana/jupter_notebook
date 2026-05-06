"""
Gatilho síncrono (com timeout) para refrescar `session_embeddings` / K-Means via tools MCP.
Complementa o cron; contagem global de sessões sem embedding (single-tenant).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import Settings, get_settings
from app.session_store import SessionStore
from mcp_client.client import Client

_logger = logging.getLogger(__name__)


def _mcp_tool_text(result: Any) -> str:
    parts: list[str] = []
    for block in getattr(result, "content", []) or []:
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            parts.append(str(block.text))
    return "\n".join(parts)


async def count_sessions_missing_embeddings(store: SessionStore) -> int:
    async with store.pool.acquire() as conn:
        v = await conn.fetchval(
            """
            SELECT COUNT(*)::int FROM sessions s
            WHERE EXISTS (
                SELECT 1 FROM conversation_messages m WHERE m.session_id = s.session_id
            )
            AND NOT EXISTS (
                SELECT 1 FROM session_embeddings e WHERE e.session_id = s.session_id
            )
            """
        )
    return int(v or 0)


async def is_kmeans_stale(store: SessionStore, ttl_days: int) -> bool:
    if ttl_days <= 0:
        return False
    async with store.pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                "SELECT last_kmeans_at FROM context_index_state WHERE tenant_key = 'default'"
            )
        except Exception as e:
            _logger.debug("context_index_state read: %s", e)
            return False
    if row is None or row["last_kmeans_at"] is None:
        return True
    cutoff = datetime.now(timezone.utc) - timedelta(days=ttl_days)
    ts = row["last_kmeans_at"]
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts < cutoff


async def _update_index_timestamps(
    store: SessionStore,
    *,
    ran_embed: bool,
    ran_kmeans: bool,
) -> None:
    if not ran_embed and not ran_kmeans:
        return
    async with store.pool.acquire() as conn:
        if ran_embed and ran_kmeans:
            await conn.execute(
                """
                UPDATE context_index_state
                SET last_embed_batch_at = NOW(), last_kmeans_at = NOW(), updated_at = NOW()
                WHERE tenant_key = 'default'
                """
            )
        elif ran_embed:
            await conn.execute(
                """
                UPDATE context_index_state
                SET last_embed_batch_at = NOW(), updated_at = NOW()
                WHERE tenant_key = 'default'
                """
            )
        elif ran_kmeans:
            await conn.execute(
                """
                UPDATE context_index_state
                SET last_kmeans_at = NOW(), updated_at = NOW()
                WHERE tenant_key = 'default'
                """
            )


async def maybe_run_sync_context_index_refresh(
    store: SessionStore,
    client: Client,
    anchor_session_id: str,
    settings: Settings | None = None,
) -> None:
    st = settings or get_settings()
    if not st.context_index_sync_enabled:
        return

    try:
        missing = await count_sessions_missing_embeddings(store)
        stale = await is_kmeans_stale(store, st.context_index_kmeans_ttl_days)
    except Exception as e:
        _logger.warning("context index probe failed: %s", e)
        return

    if missing < st.context_index_rebuild_session_threshold and not stale:
        return

    ran_embed = False
    ran_kmeans = False
    lim = max(1, min(int(st.context_index_embed_cap_per_trigger), 200))
    timeout = float(st.context_index_sync_timeout_seconds)

    async def _work() -> None:
        nonlocal ran_embed, ran_kmeans
        r1 = await client.call_tool(
            "context_embed_sessions",
            {"session_id": anchor_session_id, "limit": lim},
        )
        t1 = _mcp_tool_text(r1)
        try:
            j1 = json.loads(t1)
            if isinstance(j1, dict) and j1.get("ok") is False:
                _logger.warning("context_embed_sessions: %s", j1.get("error"))
            else:
                ran_embed = True
        except (json.JSONDecodeError, TypeError):
            ran_embed = True

        if stale or missing >= st.context_index_rebuild_session_threshold:
            r2 = await client.call_tool(
                "context_rebuild_kmeans",
                {
                    "session_id": anchor_session_id,
                    "n_clusters": int(st.context_index_kmeans_n_clusters),
                    "model_version": "kmeans_v1",
                },
            )
            t2 = _mcp_tool_text(r2)
            try:
                j2 = json.loads(t2)
                if isinstance(j2, dict) and j2.get("ok") is False:
                    _logger.warning("context_rebuild_kmeans: %s", j2.get("error"))
                else:
                    ran_kmeans = True
            except (json.JSONDecodeError, TypeError):
                ran_kmeans = True

    try:
        await asyncio.wait_for(_work(), timeout=timeout)
    except asyncio.TimeoutError:
        _logger.warning(
            "context index refresh timeout after %.1fs (missing=%s stale=%s)",
            timeout,
            missing,
            stale,
        )
        return
    except Exception as e:
        _logger.warning("context index refresh failed: %s", e)
        return

    try:
        await _update_index_timestamps(store, ran_embed=ran_embed, ran_kmeans=ran_kmeans)
    except Exception as e:
        _logger.debug("context_index_state update: %s", e)
