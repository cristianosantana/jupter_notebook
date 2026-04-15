"""Paralelismo de ``call_tool`` no especialista (orchestrator)."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.orchestrator import ModularOrchestrator
from app.virtual_tools import ANALYTICS_AGGREGATE_SESSION_TOOL_NAME


def _tc(name: str, args: dict | None = None) -> dict:
    return {
        "id": f"id-{name}",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(args or {}),
        },
    }


def test_parallel_eligible_false_when_aggregate_present(monkeypatch: pytest.MonkeyPatch):
    model = MagicMock()
    client = MagicMock()
    orch = ModularOrchestrator(model, client)
    orch.current_agent = "analise_os"
    orch._session_metadata = {"mcp_tool_cache": {"entries": []}}
    orch._session_id_for_cache = uuid4()
    monkeypatch.setattr(
        "app.orchestrator.get_settings",
        lambda: MagicMock(
            orchestrator_parallel_tool_calls_enabled=True,
        ),
    )
    tool_calls = [_tc("run_analytics_query"), _tc(ANALYTICS_AGGREGATE_SESSION_TOOL_NAME)]
    assert orch._specialist_tool_calls_parallel_mcp_eligible(tool_calls) is False


def test_parallel_gather_faster_than_sequential_sleep(monkeypatch: pytest.MonkeyPatch):
    from mcp.types import CallToolResult, TextContent  # pyright: ignore

    async def fake_bounded(self, name: str, _args: dict) -> CallToolResult:
        await asyncio.sleep(0.08)
        return CallToolResult(
            content=[TextContent(type="text", text='{"ok":true}')],
            isError=False,
        )

    model = MagicMock()
    client = MagicMock()
    orch = ModularOrchestrator(model, client)
    orch.current_agent = "analise_os"
    orch._session_metadata = {"mcp_tool_cache": {"entries": []}}
    orch._session_id_for_cache = uuid4()
    orch._append_message = MagicMock()
    orch._observer_append = MagicMock()

    monkeypatch.setattr(
        "app.orchestrator.get_settings",
        lambda: MagicMock(
            orchestrator_parallel_tool_calls_enabled=True,
            orchestrator_parallel_tool_calls_max_concurrent=4,
            orchestrator_mcp_tool_call_timeout_seconds=30.0,
            orchestrator_tool_result_preview_max=500,
            tool_message_content_max_chars=600_000,
            analytics_session_datasets_enabled=False,
        ),
    )

    monkeypatch.setattr(ModularOrchestrator, "_call_mcp_tool_bounded", fake_bounded)

    tool_calls = [_tc("get_current_time"), _tc("list_analytics_queries")]
    assert orch._specialist_tool_calls_parallel_mcp_eligible(tool_calls) is True

    tools_used: list = []

    async def _run() -> float:
        t0 = asyncio.get_event_loop().time()
        await orch._dispatch_specialist_tool_calls(tool_calls, tools_used)
        return asyncio.get_event_loop().time() - t0

    elapsed = asyncio.run(_run())
    assert elapsed < 0.22
    assert len(tools_used) == 2
    assert all(t.get("ok") for t in tools_used)
