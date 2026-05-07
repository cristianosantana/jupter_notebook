"""PostgreSQL via asyncpg — params posicionais ($1, $2, …)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import asyncpg

from orion_mcp_v3.connection_hub.abstract import AbstractDatastoreClient


def _positional(params: Sequence[Any] | Mapping[str, Any] | None) -> tuple[Any, ...]:
    if params is None:
        return ()
    if isinstance(params, Mapping):
        raise TypeError("PostgresDatastoreClient: use tupla/lista posicional ($1, $2, …)")
    return tuple(params)


def _parse_cmd_rows(status: str) -> int:
    """Extrai número de linhas afectadas a partir da string de comando asyncpg."""
    parts = status.split()
    if not parts:
        return 0
    tail = parts[-1]
    if tail.isdigit():
        return int(tail)
    return 0


class PostgresDatastoreClient(AbstractDatastoreClient):
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def select(
        self,
        query: str,
        params: Sequence[Any] | Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        args = _positional(params)
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *args)
        return [dict(r) for r in rows]

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
        args = _positional(params)
        async with self._pool.acquire() as conn:
            status = await conn.execute(query, *args)
        return _parse_cmd_rows(status)

    async def close(self) -> None:
        await self._pool.close()
