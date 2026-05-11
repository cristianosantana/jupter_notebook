from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from orion_mcp.api.main import create_app
from orion_mcp.core.config.settings import Settings, get_settings
from orion_mcp.core.context.context_builder import (
    build_context,
    cap_llm_prompt,
    effective_llm_prompt_token_cap,
)
from orion_mcp.core.orchestrator.action_executor import ActionExecutor
from orion_mcp.core.state.models import State


def test_effective_llm_prompt_token_cap_min() -> None:
    s = Settings(
        context_max_tokens=99999,
        llm_max_prompt_tokens=3000,
        llm_prompt_token_budget=None,
    )
    assert effective_llm_prompt_token_cap(s) == 3000


def test_build_context_respects_llm_max_prompt_tokens() -> None:
    s = Settings(
        context_max_tokens=50000,
        llm_max_prompt_tokens=400,
        context_section_budget_tokens=8000,
        llm_prompt_token_budget=None,
    )
    big = "w" * 8000
    st = State(short_memory=big)
    res = build_context(st, "q", s)
    assert res.context_truncated is True
    assert len(res.text) < len(big)


def test_cap_llm_prompt_truncates_suffix() -> None:
    s = Settings(
        context_max_tokens=50000,
        llm_max_prompt_tokens=256,
        llm_prompt_token_budget=None,
    )
    base = "x" * 800
    out, truncated = cap_llm_prompt(base + "\n### Extra\n" + "y" * 800, s)
    assert truncated is True
    assert len(out) < len(base) * 2


@pytest.mark.asyncio
async def test_action_executor_tool_timeout_sets_perf() -> None:
    reg = MagicMock()

    async def boom(_state: State) -> tuple[str, dict]:
        raise RuntimeError("tool_timeout") from TimeoutError()

    reg.execute_default_tool = boom
    ex = ActionExecutor(reg)
    st = State(flags={"force_refresh": True})
    out = await ex.run_call_tool(st)
    assert out.flags.get("perf", {}).get("tool_timeout") is True
    assert out.flags.get("force_refresh") is None


def test_tool_timeout_sets_perf_in_chat(monkeypatch: pytest.MonkeyPatch) -> None:
    from orion_mcp.core.tools.registry import ToolRegistry

    async def fake_execute(self: ToolRegistry, state: State) -> tuple[str, dict]:
        raise RuntimeError("tool_timeout") from TimeoutError()

    monkeypatch.setattr(ToolRegistry, "execute_default_tool", fake_execute)
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as c:
            r = c.post(
                "/api/v1/chat",
                json={"session_id": "perf-tool-to", "message": "mostra analytics", "strategy": "fast"},
            )
        assert r.status_code == 200
        perf = r.json()["payload"].get("perf") or {}
        assert perf.get("tool_timeout") is True
    finally:
        get_settings.cache_clear()


def test_chat_llm_budget_exhausted_perf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ORION_MAX_LLM_CALLS_PER_REQUEST", "0")
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as c:
            r = c.post(
                "/api/v1/chat",
                json={"session_id": "perf-budget-1", "message": "mostra analytics", "strategy": "fast"},
            )
        assert r.status_code == 200
        perf = r.json()["payload"].get("perf") or {}
        assert perf.get("llm_budget_exhausted") is True
    finally:
        get_settings.cache_clear()
