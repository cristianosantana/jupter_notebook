from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Protocol

import asyncpg

from orion_mcp.core.state.models import State

_logger = logging.getLogger(__name__)


class StateRepository(Protocol):
    async def load(self, session_id: str) -> State: ...

    async def save(self, session_id: str, state: State) -> None: ...


class PostgresStateRepository:
    def __init__(self, pool: asyncpg.Pool):
        self._pool = pool

    async def load(self, session_id: str) -> State:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT state FROM conversation_state WHERE session_id = $1",
                session_id,
            )
        if not row:
            return State()
        data = row["state"]
        if isinstance(data, str):
            data = json.loads(data)
        return State.model_validate(data)

    async def save(self, session_id: str, state: State) -> None:
        payload = state.model_dump(mode="json")
        now = datetime.now(timezone.utc)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO conversation_state (session_id, state, updated_at)
                VALUES ($1, $2::jsonb, $3)
                ON CONFLICT (session_id) DO UPDATE
                SET state = EXCLUDED.state, updated_at = EXCLUDED.updated_at
                """,
                session_id,
                json.dumps(payload),
                now,
            )


class MemoryStateRepository:
    def __init__(self) -> None:
        self._store: dict[str, State] = {}

    async def load(self, session_id: str) -> State:
        s = self._store.get(session_id)
        return State() if s is None else s.model_copy(deep=True)

    async def save(self, session_id: str, state: State) -> None:
        self._store[session_id] = state.model_copy(deep=True)
