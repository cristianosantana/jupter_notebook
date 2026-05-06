from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Protocol

import asyncpg

from orion_mcp.core.state.models import State

_logger = logging.getLogger(__name__)

_PERSIST_DATASET_LIST_CAP = 64
_EPHEMERAL_FLAG_KEYS = frozenset({"pending_domain_tool_cache_key", "_orion_drl_log_session_id"})


def _strip_ephemeral_flags(payload: dict[str, Any]) -> None:
    f = payload.get("flags")
    if not isinstance(f, dict):
        return
    payload["flags"] = {k: v for k, v in f.items() if k not in _EPHEMERAL_FLAG_KEYS}


def _shrink_datasets_for_persist(datasets: Any) -> Any:
    if not isinstance(datasets, dict):
        return datasets
    out: dict[str, Any] = {}
    for k, v in list(datasets.items())[:16]:
        if isinstance(v, list) and len(v) > _PERSIST_DATASET_LIST_CAP:
            out[str(k)] = {
                "rows_preview": v[:_PERSIST_DATASET_LIST_CAP],
                "truncated": True,
                "len": len(v),
            }
        else:
            out[str(k)] = v
    return out


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
        _strip_ephemeral_flags(payload)
        if isinstance(payload.get("datasets"), dict):
            payload["datasets"] = _shrink_datasets_for_persist(payload["datasets"])
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
        payload = state.model_dump(mode="json")
        _strip_ephemeral_flags(payload)
        if isinstance(payload.get("datasets"), dict):
            payload["datasets"] = _shrink_datasets_for_persist(payload["datasets"])
        self._store[session_id] = State.model_validate(payload)
