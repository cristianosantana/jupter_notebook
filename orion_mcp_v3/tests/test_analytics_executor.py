"""Fase 1.5 — AnalyticsExecutor (planner + compilador + MySQL mock)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from orion_mcp_v3.broker import AnalyticsExecutor
from orion_mcp_v3.config.allowlists import ANALYTICS_ALLOWLIST


def _executor_with_mock_rows(rows: list[dict]) -> tuple[AnalyticsExecutor, AsyncMock]:
    mysql = MagicMock()
    mysql.select = AsyncMock(return_value=rows)
    ex = AnalyticsExecutor(mysql, ANALYTICS_ALLOWLIST, default_limit=1000)
    return ex, mysql.select


def test_execute_simple_query_returns_rows_and_sql() -> None:
    rows = [{"id": 1, "data_venda": "2024-01-01", "valor": 10.0, "status": "ok"}]
    executor, select_mock = _executor_with_mock_rows(rows)

    async def run() -> None:
        result = await executor.execute(
            "últimos 3 meses faturamento",
            intent_slug="analytics.temporal",
        )
        assert result.row_count > 0
        assert "SELECT" in result.sql
        assert "LIMIT" in result.sql
        assert result.rows == rows
        assert result.plan.hints.get("aggregation_kind") == "temporal"

    asyncio.run(run())
    select_mock.assert_awaited_once()


def test_execute_accepts_sql_hints_override_table() -> None:
    executor, select_mock = _executor_with_mock_rows([{"id": 1, "nome": "x"}])

    async def run() -> None:
        result = await executor.execute(
            "lista",
            sql_hints={"sql_table": "clientes", "sql_columns": ("id", "nome", "created_at")},
        )
        assert result.row_count == 1
        args, kwargs = select_mock.await_args
        sql = args[0]
        assert "`clientes`" in sql

    asyncio.run(run())


def test_execute_propagates_compiled_params() -> None:
    executor, select_mock = _executor_with_mock_rows([])

    async def run() -> None:
        await executor.execute(
            "teste",
            sql_hints={
                "sql_table": "os",
                "sql_columns": ("created_at",),
                "limit": 10,
            },
        )
        assert select_mock.await_args is not None
        params = select_mock.await_args.kwargs["params"]
        assert params[-1] == 10

    asyncio.run(run())
