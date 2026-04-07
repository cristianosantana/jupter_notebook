"""Trace: truncagem, session_id, llm_phase, sampling completo."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent_trace import (
    AgentTraceLogger,
    activate_openai_chat_stats_for_run,
    get_openai_chat_stats,
    get_trace_llm_phase,
    llm_phase_context,
    take_openai_chat_stats,
)


def test_agent_trace_no_truncation_when_max_zero(tmp_path: Path) -> None:
    log = tmp_path / "d" / "h" / "run_app.jsonl"
    log.parent.mkdir(parents=True)
    logger = AgentTraceLogger(
        run_id="r1",
        app_log_path=log,
        max_value_chars=0,
        session_id="550e8400-e29b-41d4-a716-446655440000",
    )
    big = "x" * 50_000
    logger.record("test.event", payload=big)
    line = log.read_text(encoding="utf-8").strip()
    data = json.loads(line)
    assert data["session_id"] == "550e8400-e29b-41d4-a716-446655440000"
    assert data["run_id"] == "r1"
    assert data["event"] == "test.event"
    assert len(data["payload"]) == 50_000


def test_agent_trace_truncates_when_positive(tmp_path: Path) -> None:
    log = tmp_path / "d" / "h" / "run_app.jsonl"
    log.parent.mkdir(parents=True)
    logger = AgentTraceLogger(
        run_id="r2",
        app_log_path=log,
        max_value_chars=100,
        session_id=None,
    )
    logger.record("t", s="a" * 200)
    data = json.loads(log.read_text(encoding="utf-8").strip())
    assert data["session_id"] is None
    assert "truncado" in data["s"]


def test_openai_chat_stats_accumulator_and_summary_fields() -> None:
    assert get_openai_chat_stats() is None
    activate_openai_chat_stats_for_run()
    s = get_openai_chat_stats()
    assert s is not None
    assert s.begin_request() == 1
    assert s.begin_request() == 2
    s.complete_response("orchestrator:maestro", 1.0)
    s.complete_response("pipeline_verifier", 0.5)
    fields = s.to_summary_fields()
    assert fields["calls_initiated"] == 2
    assert fields["calls_completed"] == 2
    assert fields["calls_by_llm_phase"]["orchestrator:maestro"] == 1
    assert fields["calls_by_llm_phase"]["pipeline_verifier"] == 1
    assert fields["total_duration_ms"] == 1500.0
    taken = take_openai_chat_stats()
    assert taken is s
    assert get_openai_chat_stats() is None


def test_openai_chat_stats_incomplete_request_no_complete() -> None:
    activate_openai_chat_stats_for_run()
    s = get_openai_chat_stats()
    assert s is not None
    s.begin_request()
    fields = s.to_summary_fields()
    assert fields["calls_initiated"] == 1
    assert fields["calls_completed"] == 0
    take_openai_chat_stats()


def test_llm_phase_context_nested() -> None:
    assert get_trace_llm_phase() is None
    with llm_phase_context("outer"):
        assert get_trace_llm_phase() == "outer"
        with llm_phase_context("inner"):
            assert get_trace_llm_phase() == "inner"
        assert get_trace_llm_phase() == "outer"
    assert get_trace_llm_phase() is None


def test_mcp_sampling_records_full_messages_not_preview() -> None:
    import mcp.types as types

    from app.mcp_sampling import build_openai_sampling_callback

    captured: list[tuple[str, dict]] = []

    class FakeLogger:
        run_id = "trace-run"

        def record(self, event: str, **fields: object) -> None:
            captured.append((event, dict(fields)))

    fake_tr = FakeLogger()
    long_text = "Z" * 12_000
    mock_resp = MagicMock()
    mock_resp.choices = [MagicMock()]
    mock_resp.choices[0].message.content = long_text
    mock_resp.model = "gpt-test"

    oai = MagicMock()
    oai.chat.completions.create = AsyncMock(return_value=mock_resp)

    cb = build_openai_sampling_callback(oai, "gpt-test")
    params = types.CreateMessageRequestParams(
        messages=[
            types.SamplingMessage(
                role="user",
                content=types.TextContent(type="text", text="hello body"),
            )
        ],
        maxTokens=100,
        temperature=0.2,
        systemPrompt="sys here",
    )

    async def _run() -> types.CreateMessageResult | types.ErrorData:
        with patch("app.mcp_sampling.get_trace_logger", return_value=fake_tr):
            ctx = MagicMock()
            return await cb(ctx, params)

    out = asyncio.run(_run())

    assert isinstance(out, types.CreateMessageResult)
    req_events = [c for c in captured if c[0] == "mcp.sampling.request"]
    res_events = [c for c in captured if c[0] == "mcp.sampling.response"]
    assert len(req_events) == 1
    assert len(res_events) == 1
    _, req_f = req_events[0]
    assert req_f["llm_phase"] == "mcp_sampling"
    assert "messages" in req_f
    assert any("hello body" in str(m.get("content", "")) for m in req_f["messages"])
    _, res_f = res_events[0]
    assert res_f["text"] == long_text
    assert res_f["text_chars"] == 12_000
    assert "preview" not in res_f


def test_openai_provider_llm_phase_in_trace() -> None:
    from ai_provider.openai_provider import OpenAIProvider

    calls: list[dict] = []

    class TL:
        run_id = "r"

        def record(self, event: str, **kw: object) -> None:
            calls.append({"event": event, **kw})

    mock_completion = MagicMock()
    mock_completion.choices = [MagicMock()]
    mock_completion.choices[0].message.role = "assistant"
    mock_completion.choices[0].message.content = "ok"
    mock_completion.choices[0].message.tool_calls = None
    mock_completion.model = "m1"

    async def _run() -> dict:
        with (
            patch("ai_provider.openai_provider.get_trace_logger", return_value=TL()),
            patch(
                "ai_provider.openai_provider.get_trace_llm_phase",
                return_value="memory:session-notes.md",
            ),
            patch.object(OpenAIProvider, "__init__", lambda self: None),
        ):
            p = OpenAIProvider.__new__(OpenAIProvider)
            p.client = MagicMock()
            p.client.chat.completions.create = AsyncMock(return_value=mock_completion)
            p.model = "default-model"
            return await p.chat([{"role": "user", "content": "hi"}], tools=None)

    out = asyncio.run(_run())
    assert out.get("content") == "ok"
    req = next(c for c in calls if c["event"] == "llm.request")
    res = next(c for c in calls if c["event"] == "llm.response")
    assert req["llm_phase"] == "memory:session-notes.md"
    assert res["llm_phase"] == "memory:session-notes.md"


def test_mcp_server_trace_no_truncation_when_env_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import mcp_server.trace_logging as tl

    monkeypatch.setenv("AGENT_TRACE_DIR", str(tmp_path))
    monkeypatch.setenv("AGENT_TRACE_MAX_FIELD_CHARS", "0")
    big = "B" * 80_000
    tl.trace_record("srv.test", run_id="rid1", payload=big)
    files = list(tmp_path.rglob("rid1_server.jsonl"))
    assert len(files) == 1
    data = json.loads(files[0].read_text(encoding="utf-8").strip())
    assert len(data["payload"]) == 80_000
