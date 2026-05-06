import pytest
from pydantic import ValidationError

from orion_mcp.core.config.settings import Settings
from orion_mcp.mcp_adapter.queries import analytics_sql
from orion_mcp.mcp_adapter.server.config import McpGrpcServerSettings


def test_settings_tool_llm_preview_rows_accepts_5000() -> None:
    s = Settings.model_validate({"tool_llm_preview_rows": 5000})
    assert s.tool_llm_preview_rows == 5000


def test_settings_tool_llm_preview_rows_rejects_above_10000() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"tool_llm_preview_rows": 10001})


def test_mcp_server_settings_same_field() -> None:
    s = McpGrpcServerSettings.model_validate({"tool_llm_preview_rows": 5000})
    assert s.tool_llm_preview_rows == 5000


def test_compact_payload_sample_rows_cap() -> None:
    from orion_mcp.core.data_engine.pipeline import build_drl_bundle

    rows = [{"id": i} for i in range(100)]
    drl = build_drl_bundle(rows, query_id="qid", log_session_id=None)
    out = analytics_sql._compact_payload(
        "qid",
        "table",
        rows,
        limit=100,
        offset=0,
        sample_rows=15,
        drl=drl,
        include_raw_rows=True,
    )
    assert len(out["rows_sample"]) == 15
    assert out.get("include_raw_rows") is True
    assert isinstance(out.get("drl_summary"), dict)
