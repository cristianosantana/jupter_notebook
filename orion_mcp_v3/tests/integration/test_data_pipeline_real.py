"""Fase 2.5 — DataPipeline sobre :class:`AnalyticsResult` (dados mock, sem MySQL real)."""

from __future__ import annotations

import asyncio

from orion_mcp_v3.broker import AnalyticsResult, DataPipeline
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy, SemanticQueryPlan


def _result(rows: list[dict], *, intent: str = "analytics.temporal") -> AnalyticsResult:
    plan = SemanticQueryPlan(
        intent_slug=intent,
        strategy=RetrievalStrategy.BROKER_FANOUT,
        hints={},
    )
    return AnalyticsResult(
        plan=plan,
        sql='SELECT "id", "valor" FROM "vendas" LIMIT %s',
        rows=rows,
        row_count=len(rows),
    )


def test_pipeline_with_mock_mysql_like_rows() -> None:
    rows = [
        {"id": 1, "valor": 10.0, "status": "a"},
        {"id": 2, "valor": 500.0, "status": "a"},
        {"id": 3, "valor": 20.0, "status": "b"},
        {"id": 4, "valor": 15.0, "status": "b"},
        {"id": 5, "valor": 12.0, "status": "c"},
        {"id": 6, "valor": 11.0, "status": "c"},
    ]
    result = _result(rows)

    async def run() -> None:
        pipeline = DataPipeline()
        output = await pipeline.process(result)
        assert output["row_count"] > 0
        assert "schema" in output
        assert output["schema"]["valor"] == "numeric"
        assert "summary" in output
        assert "valor" in output["summary"]
        assert len(output["sample"]) > 0
        cov = output["coverage"]
        assert cov.labels.get("total_rows") == 6
        assert cov.labels.get("schema_fields") == len(output["schema"])

    asyncio.run(run())


def test_pipeline_empty_rows() -> None:
    result = _result([])

    async def run() -> None:
        out = await DataPipeline().process(result)
        assert out["row_count"] == 0
        assert out["schema"] == {}
        assert out["sample"] == []

    asyncio.run(run())


def test_pipeline_high_variance_insight() -> None:
    rows = [{"id": i, "valor": float(v)} for i, v in enumerate([1.0, 1.0, 100.0], start=1)]
    result = _result(rows)

    async def run() -> None:
        out = await DataPipeline().process(result)
        assert any("variância" in x for x in out["insights"])

    asyncio.run(run())
