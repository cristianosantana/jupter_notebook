"""C2: tools MCP com executor mockado (sem MySQL real)."""

from __future__ import annotations

from typing import Any

import pytest


class _DummyPool:
    """Compatível com close_mysql_pool do pacote mysql."""

    def close(self) -> None:
        pass

    async def wait_closed(self) -> None:
        return None


@pytest.mark.asyncio
async def test_run_analytics_query_tool_allowlisted(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create_mysql_pool(url: str | None, **_: Any) -> Any:
        _ = url
        return _DummyPool()

    async def fake_run_catalog_select(
        pool: Any,
        sql_inner: str,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        _ = pool, sql_inner, limit, offset
        return [{"demo": 42}]

    monkeypatch.setattr(
        "orion_mcp_v2.mcp_server_standalone.server.create_mysql_pool",
        fake_create_mysql_pool,
    )
    monkeypatch.setattr(
        "orion_mcp_v2.db.mysql.query_executor.run_catalog_select",
        fake_run_catalog_select,
    )

    from fastmcp import Client

    from orion_mcp_v2.mcp_server_standalone.server import build_mcp_server

    mcp = build_mcp_server()
    async with Client(mcp) as client:
        result = await client.call_tool(
            "run_analytics_query",
            {
                "query_id": "ticket_medio_concessionaria_agg",
                "date_from": "2026-01-01",
                "date_to": "2026-01-31",
                "limit": 100,
                "offset": 0,
            },
        )
        assert result.is_error is False
        text_parts = [getattr(b, "text", "") or "" for b in (result.content or [])]
        blob = "".join(text_parts)
        assert "demo" in blob or "42" in blob

        bad = await client.call_tool(
            "run_analytics_query",
            {"query_id": "__invalid_query__"},
            raise_on_error=False,
        )
        assert bad.is_error is True


@pytest.mark.asyncio
async def test_aggregate_for_query_id_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create_mysql_pool(url: str | None, **_: Any) -> Any:
        _ = url
        return _DummyPool()

    async def fake_run_catalog_select(
        pool: Any,
        sql_inner: str,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        _ = pool, sql_inner, limit, offset
        return [
            {
                "servico_A_id": 1,
                "servico_B_id": 2,
                "frequencia_combo": 3,
                "receita_combo": 30.0,
            },
        ]

    monkeypatch.setattr(
        "orion_mcp_v2.mcp_server_standalone.server.create_mysql_pool",
        fake_create_mysql_pool,
    )
    monkeypatch.setattr(
        "orion_mcp_v2.db.mysql.query_executor.run_catalog_select",
        fake_run_catalog_select,
    )

    from fastmcp import Client

    from orion_mcp_v2.mcp_server_standalone.server import build_mcp_server

    mcp = build_mcp_server()
    async with Client(mcp) as client:
        result = await client.call_tool(
            "aggregate_for_query_id",
            {
                "query_id": "cross_selling",
                "date_from": "2026-01-01",
                "date_to": "2026-01-31",
            },
        )
        assert result.is_error is False
        text_parts = [getattr(b, "text", "") or "" for b in (result.content or [])]
        blob = "".join(text_parts)
        assert "aggregate" in blob or "receita" in blob or "30" in blob

        bad = await client.call_tool(
            "aggregate_for_query_id",
            {"query_id": "ticket_medio_concessionaria_agg"},
            raise_on_error=False,
        )
        assert bad.is_error is True


@pytest.mark.asyncio
async def test_list_analytics_queries_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create_mysql_pool(url: str | None, **_: Any) -> Any:
        _ = url
        return _DummyPool()

    monkeypatch.setattr(
        "orion_mcp_v2.mcp_server_standalone.server.create_mysql_pool",
        fake_create_mysql_pool,
    )

    from fastmcp import Client

    from orion_mcp_v2.db.mysql.sql_catalog import QUERY_IDS
    from orion_mcp_v2.mcp_server_standalone.server import build_mcp_server

    mcp = build_mcp_server()
    async with Client(mcp) as client:
        result = await client.call_tool("list_analytics_queries", {})
        assert result.is_error is False
        text_parts = [getattr(b, "text", "") or "" for b in (result.content or [])]
        blob = "".join(text_parts)
        assert QUERY_IDS[0] in blob or "ticket_medio" in blob


@pytest.mark.asyncio
async def test_tools_declare_read_only_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_create_mysql_pool(url: str | None, **_: Any) -> Any:
        _ = url
        return _DummyPool()

    monkeypatch.setattr(
        "orion_mcp_v2.mcp_server_standalone.server.create_mysql_pool",
        fake_create_mysql_pool,
    )

    from fastmcp import Client

    from orion_mcp_v2.mcp_server_standalone.server import build_mcp_server

    mcp = build_mcp_server()
    async with Client(mcp) as client:
        tools = await client.list_tools()
        by_name = {t.name: t for t in tools}
        ra = by_name["run_analytics_query"].annotations
        assert ra is not None
        assert getattr(ra, "readOnlyHint", None) is True
