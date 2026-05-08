"""Fase 3.5 — AnalyticalContextBuilder (pipeline mock + allocate)."""

from __future__ import annotations

import asyncio

from orion_mcp_v3.contracts.context_block import ContextRole
from orion_mcp_v3.runtime.context_builder import AnalyticalContextBuilder


def _pipeline_stub() -> dict:
    return {
        "schema": {"valor": "numeric"},
        "row_count": 4,
        "summary": {"valor": {"media": 12.5, "min": 1.0, "max": 40.0, "count": 4}},
        "sample": [{"id": 1, "valor": 10.0}],
        "insights": [],
    }


def test_context_builder_system_data_and_memory_order() -> None:
    pipeline_output = _pipeline_stub()

    async def run() -> None:
        builder = AnalyticalContextBuilder()
        blocks = await builder.build(
            pipeline_output,
            memory_curta={"insights": ["Crescimento +12%"]},
            token_budget=4000,
        )
        assert len(blocks) >= 2
        assert blocks[0].role == ContextRole.SYSTEM
        assert blocks[1].role == ContextRole.DATA
        if len(blocks) >= 3:
            assert blocks[2].role == ContextRole.CONTEXT

    asyncio.run(run())


def test_context_builder_without_memory_two_blocks() -> None:
    async def run() -> None:
        blocks = await AnalyticalContextBuilder().build(_pipeline_stub(), token_budget=4000)
        roles = [b.role for b in blocks]
        assert ContextRole.SYSTEM in roles
        assert ContextRole.DATA in roles
        assert ContextRole.CONTEXT not in roles

    asyncio.run(run())


def test_context_builder_includes_user_id_in_system_text() -> None:
    async def run() -> None:
        blocks = await AnalyticalContextBuilder().build(
            _pipeline_stub(),
            user_id="u-42",
            token_budget=4000,
        )
        assert blocks[0].role == ContextRole.SYSTEM
        assert "u-42" in blocks[0].text

    asyncio.run(run())
