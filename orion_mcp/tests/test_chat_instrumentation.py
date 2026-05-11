from pathlib import Path

from orion_mcp.core.config.settings import Settings
from orion_mcp.core.orchestrator.chat_instrumentation import (
    build_llm_halt_debug_extra,
    sem_cache_marker_in,
    snapshot_state_for_instrumentation,
    write_trace_llm_context_file,
)
from orion_mcp.core.state.models import DataCacheEntry, State


def test_sem_cache_marker() -> None:
    assert sem_cache_marker_in("### Dados resumidos\n(sem cache de dados)\n")
    assert not sem_cache_marker_in("rows=1")


def test_snapshot_state_includes_cache_previews() -> None:
    st = State(
        intent="general",
        data_cache={"k1": DataCacheEntry(summary="hello world")},
        entities={"task_profile": {"a": 1}},
        flags={"perf": {"tool_timeout": True}},
    )
    snap = snapshot_state_for_instrumentation(
        st,
        decision_action="GENERATE_RESPONSE",
        tool_calls=1,
        llm_calls=0,
        user_input="hi",
        elapsed_ms_since_turn_start=12,
    )
    assert snap["data_cache_entry_count"] == 1
    assert snap["metrics_tool_calls"] == 1
    assert "hello" in snap["data_cache_summaries"][0]["summary_head"]


def test_build_llm_halt_debug_extra_structure() -> None:
    st = State(data_cache={"x": DataCacheEntry(summary="s")})
    extra = build_llm_halt_debug_extra(
        state=st,
        session_id="sid",
        user_input="q",
        decision_action="GENERATE_RESPONSE",
        metrics={"tool_calls": 1},
        budget_llm_calls=0,
        transport="chat",
        halt_kind="chat_completion",
        ctx_res_text="### Dados resumidos\n(sem cache de dados)",
        ctx_text_final="### Dados resumidos\n(sem cache de dados)",
        context_truncated_from_builder=False,
        cap_llm_truncated=False,
        elapsed_ms_since_turn_start=5,
    )
    assert extra["halt_kind"] == "chat_completion"
    assert extra["context_pipeline"]["raw_has_sem_cache_marker"] is True
    assert extra["state_at_llm_gate"]["data_cache_entry_count"] == 1


def test_write_trace_llm_context_file_creates_txt(tmp_path: Path) -> None:
    s = Settings.model_validate(
        {
            "orchestrator_chat_trace": True,
            "llm_debug_log_dir": str(tmp_path),
        }
    )
    out = write_trace_llm_context_file(
        s,
        session_id="sid-1",
        transport="chat",
        kind="chat_completion",
        system_prompt="SYS",
        user_content="USERCTX",
    )
    assert out is not None
    p = Path(out)
    assert p.is_file()
    text = p.read_text(encoding="utf-8")
    assert "SYS" in text and "USERCTX" in text


def test_write_trace_llm_context_file_skipped_when_trace_off(tmp_path: Path) -> None:
    s = Settings.model_validate(
        {
            "orchestrator_chat_trace": False,
            "llm_debug_log_dir": str(tmp_path),
        }
    )
    assert (
        write_trace_llm_context_file(
            s,
            session_id="x",
            transport="chat",
            kind="chat_completion",
            system_prompt="a",
            user_content="b",
        )
        is None
    )
