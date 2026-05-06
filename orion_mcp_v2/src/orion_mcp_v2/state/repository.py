from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import asyncpg

from orion_mcp_v2.state.models import ConversationStateV2, Message

_logger = logging.getLogger(__name__)


def _parse_last_data(raw: Any) -> dict[str, Any] | None:
    """JSONB pode vir como dict (asyncpg) ou como str em alguns caminhos/drivers."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return dict(raw)
    if isinstance(raw, (bytes, bytearray)):
        try:
            raw = raw.decode()
        except Exception:
            return None
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            _logger.warning("last_data_invalid_json", extra={"snippet": raw[:120]})
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _coerce_json_value(raw: Any) -> Any:
    """Deserializa JSON em string (ex.: coluna lida como texto)."""
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw
    return raw


def _parse_messages(raw: Any) -> list[Message]:
    if not isinstance(raw, list):
        return []
    out: list[Message] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant", "system") or not isinstance(content, str):
            continue
        ts = item.get("ts")
        parsed_ts = None
        if isinstance(ts, str):
            try:
                parsed_ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            except ValueError:
                parsed_ts = None
        out.append(Message(role=role, content=content, ts=parsed_ts))
    return out


class StateRepository:
    def __init__(self, pool: asyncpg.Pool | None):
        self._pool = pool

    async def ensure_user(self, user_id: str) -> None:
        if self._pool is None:
            return
        async with self._pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING",
                user_id,
            )

    async def load(self, session_id: str) -> ConversationStateV2 | None:
        if self._pool is None:
            return None
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT session_id, user_id, messages, last_data, last_query_signature,
                       state_status, created_at, updated_at
                FROM conversation_state WHERE session_id = $1
                """,
                session_id,
            )
        if row is None:
            return None
        return ConversationStateV2(
            session_id=row["session_id"],
            user_id=row["user_id"],
            messages=_parse_messages(_coerce_json_value(row["messages"])),
            last_data=_parse_last_data(row["last_data"]),
            last_query_signature=row["last_query_signature"],
            state_status=row["state_status"] or "active",
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def save(self, state: ConversationStateV2) -> None:
        if self._pool is None:
            _logger.warning("state_save_skipped_no_pg")
            return
        await self.ensure_user(state.user_id)
        payload_messages = [
            {"role": m.role, "content": m.content, "ts": (m.ts.isoformat() if m.ts else None)}
            for m in state.messages
        ]
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO conversation_state (
                  session_id, user_id, messages, last_data, last_query_signature,
                  state_status, created_at, updated_at
                ) VALUES ($1,$2,$3::jsonb,$4::jsonb,$5,$6,$7,$8)
                ON CONFLICT (session_id) DO UPDATE SET
                  user_id = EXCLUDED.user_id,
                  messages = EXCLUDED.messages,
                  last_data = EXCLUDED.last_data,
                  last_query_signature = EXCLUDED.last_query_signature,
                  state_status = EXCLUDED.state_status,
                  created_at = conversation_state.created_at,
                  updated_at = EXCLUDED.updated_at
                """,
                state.session_id,
                state.user_id,
                json.dumps(payload_messages),
                json.dumps(state.last_data) if state.last_data is not None else None,
                state.last_query_signature,
                state.state_status,
                state.created_at or now,
                now,
            )

    async def list_sessions_for_user(
        self,
        user_id: str,
        *,
        since: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Para jobs de consolidação: sessões recentes."""
        if self._pool is None:
            return []
        async with self._pool.acquire() as conn:
            if since:
                rows = await conn.fetch(
                    """
                    SELECT session_id, messages, created_at, updated_at
                    FROM conversation_state
                    WHERE user_id = $1 AND created_at >= $2
                    ORDER BY updated_at DESC
                    """,
                    user_id,
                    since,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT session_id, messages, created_at, updated_at
                    FROM conversation_state
                    WHERE user_id = $1
                    ORDER BY updated_at DESC
                    """,
                    user_id,
                )
        return [dict(r) for r in rows]

    async def delete_sessions_before(self, user_id: str, cutoff: datetime) -> int:
        if self._pool is None:
            return 0
        async with self._pool.acquire() as conn:
            r = await conn.execute(
                """
                DELETE FROM conversation_state
                WHERE user_id = $1 AND created_at < $2
                """,
                user_id,
                cutoff,
            )
        # asyncpg returns "DELETE N"
        parts = str(r).split()
        return int(parts[-1]) if parts else 0

    async def list_distinct_user_ids(self) -> list[str]:
        if self._pool is None:
            return []
        async with self._pool.acquire() as conn:
            rows = await conn.fetch("SELECT DISTINCT user_id FROM conversation_state")
        return [r["user_id"] for r in rows]
