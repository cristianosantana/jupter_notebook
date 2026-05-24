"""Fase 0.5 — Connection Hub: pools MySQL/Postgres/Redis e clientes (mock async)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orion_mcp_v3.connection_hub.mysql_backend import MysqlDatastoreClient
from orion_mcp_v3.connection_hub.postgres_backend import PostgresDatastoreClient
from orion_mcp_v3.connection_hub.pools import (
    close_mysql_pool,
    create_mysql_pool,
    create_postgres_pool,
    create_redis_client,
)
from orion_mcp_v3.connection_hub.redis_backend import RedisDatastoreClient


class _AsyncCM:
    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(self, *args: object) -> None:
        return None


def _mysql_pool_with_cursor(rows: list[dict]) -> MagicMock:
    pool = MagicMock()
    cur = MagicMock()
    cur.execute = AsyncMock()
    cur.fetchall = AsyncMock(return_value=rows)
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=_AsyncCM(cur))
    pool.acquire = MagicMock(return_value=_AsyncCM(conn))
    return pool


@pytest.fixture
def mysql_select_rows() -> list[dict]:
    return [{"id": 1, "name": "x"}]


def test_create_mysql_pool_returns_none_when_url_empty() -> None:
    assert asyncio.run(create_mysql_pool(None)) is None
    assert asyncio.run(create_mysql_pool("")) is None
    assert asyncio.run(create_mysql_pool("   ")) is None


def test_create_mysql_pool_calls_asyncmy_with_parsed_url() -> None:
    fake_pool = MagicMock()

    async def _run() -> None:
        with patch("asyncmy.create_pool", new_callable=AsyncMock, return_value=fake_pool) as m:
            out = await create_mysql_pool(
                "mysql://user:p%40ss@db.example.com:3307/appdb",
                minsize=2,
                maxsize=5,
            )
        assert out is fake_pool
        m.assert_awaited_once()
        kw = m.await_args.kwargs
        assert kw["host"] == "db.example.com"
        assert kw["port"] == 3307
        assert kw["user"] == "user"
        assert kw["password"] == "p@ss"
        assert kw["db"] == "appdb"
        assert kw["minsize"] == 2
        assert kw["maxsize"] == 5
        assert kw["autocommit"] is True

    asyncio.run(_run())


def test_mysql_client_select_uses_dict_cursor(mysql_select_rows: list[dict]) -> None:
    pool = _mysql_pool_with_cursor(mysql_select_rows)
    client = MysqlDatastoreClient(pool)

    async def run() -> None:
        rows = await client.select("SELECT id, name FROM t WHERE id = %s", (1,))
        assert rows == mysql_select_rows

    asyncio.run(run())
    pool.acquire.assert_called_once()


def test_mysql_client_mutation_returns_rowcount() -> None:
    pool = MagicMock()
    cur = MagicMock()
    cur.execute = AsyncMock()
    cur.rowcount = 3
    conn = MagicMock()
    conn.cursor = MagicMock(return_value=_AsyncCM(cur))
    pool.acquire = MagicMock(return_value=_AsyncCM(conn))
    client = MysqlDatastoreClient(pool)

    async def run() -> None:
        n = await client.insert("INSERT INTO logs (msg) VALUES (%s)", ("ok",))
        assert n == 3

    asyncio.run(run())


def test_close_mysql_pool_noop_for_none() -> None:
    asyncio.run(close_mysql_pool(None))


def test_postgres_select_rejects_mapping_params() -> None:
    pool = MagicMock()
    pg = PostgresDatastoreClient(pool)

    async def run() -> None:
        with pytest.raises(TypeError, match="tupla"):
            await pg.select("SELECT 1", {"x": 1})

    asyncio.run(run())


def test_redis_client_rejects_mapping_params() -> None:
    rcli = MagicMock()
    rd = RedisDatastoreClient(rcli)

    async def run() -> None:
        with pytest.raises(TypeError, match="tupla"):
            await rd.select("GET", {"k": "bad"})

    asyncio.run(run())


def test_create_postgres_pool_none_on_empty_url() -> None:
    assert asyncio.run(create_postgres_pool(None)) is None


def test_create_redis_client_none_on_empty_url() -> None:
    assert asyncio.run(create_redis_client("")) is None
