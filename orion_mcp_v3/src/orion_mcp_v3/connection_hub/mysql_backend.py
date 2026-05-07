"""MySQL via asyncmy — params posicionais (%s)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from asyncmy.cursors import DictCursor

from orion_mcp_v3.connection_hub.abstract import AbstractDatastoreClient


def _exec_args(params: Sequence[Any] | Mapping[str, Any] | None) -> tuple[Any, ...] | dict[str, Any]:
    if params is None:
        return ()
    if isinstance(params, Mapping):
        return dict(params)
    return tuple(params)


class MysqlDatastoreClient(AbstractDatastoreClient):
    def __init__(self, pool: Any) -> None:
        self._pool = pool

    async def select(
        self,
        query: str,
        params: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        args = _exec_args(params)
        async with self._pool.acquire() as conn:
            async with conn.cursor(DictCursor) as cur:
                await cur.execute(query, args)
                rows = await cur.fetchall()
        return list(rows) if rows else []

    async def insert(
        self,
        query: str,
        params: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> int:
        return await self._execute_mutation(query, params)

    async def update(
        self,
        query: str,
        params: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> int:
        return await self._execute_mutation(query, params)

    async def delete(
        self,
        query: str,
        params: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> int:
        return await self._execute_mutation(query, params)

    async def _execute_mutation(
        self,
        query: str,
        params: Sequence[Any] | Mapping[str, Any] | None,
    ) -> int:
        args = _exec_args(params)
        async with self._pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(query, args)
                return int(cur.rowcount or 0)

    async def close(self) -> None:
        self._pool.close()
        await self._pool.wait_closed()
