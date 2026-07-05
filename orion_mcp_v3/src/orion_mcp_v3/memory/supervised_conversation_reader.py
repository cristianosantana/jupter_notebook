"""Leitura read-only das conversas supervisionadas já produzidas pelo chat."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Sequence

import asyncpg

from orion_mcp_v3.memory.remissive_models import RemissiveConversationWindow


_READ_WINDOW = """
SELECT
    cs.session_id::text AS session_id,
    COALESCE(cs.user_id, 'sistema_background') AS user_id,
    cs.messages,
    COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'message_id', cte.message_id,
                'role', cte.role,
                'content', cte.content,
                'created_at', cte.created_at
            )
            ORDER BY cte.created_at ASC
        ) FILTER (WHERE cte.id IS NOT NULL),
        '[]'::jsonb
    ) AS indexed_turns
FROM conversation_state cs
LEFT JOIN chat_turn_embeddings cte
    ON cte.session_id = cs.session_id::text
    AND cte.created_at >= $1
    AND cte.created_at < $2
WHERE cs.created_at >= $1
  AND cs.created_at < $2
  AND cs.distilled_at IS NULL
GROUP BY cs.session_id, cs.user_id, cs.messages, cs.created_at
ORDER BY cs.created_at ASC
LIMIT $3
"""

_MARK_PROCESSED = """
UPDATE conversation_state
SET distilled_at = now()
WHERE session_id = ANY($1::uuid[])
"""


def _as_sequence(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


class SupervisedConversationReader:
    """Leitor read-only para o comando externo de destilação remissiva."""

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def read_window(
        self,
        start: datetime,
        end: datetime,
        *,
        limit: int = 500,
    ) -> list[RemissiveConversationWindow]:
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(_READ_WINDOW, start, end, max(1, limit))

        return [
            RemissiveConversationWindow(
                session_id=str(row["session_id"]),
                user_id=str(row["user_id"] or "sistema_background"),
                messages=_as_sequence(row["messages"]),
                indexed_turns=_as_sequence(row["indexed_turns"]),
            )
            for row in rows
        ]

    async def mark_processed(self, windows: Sequence[RemissiveConversationWindow]) -> None:
        session_ids = [window.session_id for window in windows if window.session_id]
        if not session_ids:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(_MARK_PROCESSED, session_ids)
