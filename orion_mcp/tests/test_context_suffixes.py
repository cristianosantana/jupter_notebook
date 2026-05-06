from orion_mcp.core.config.settings import Settings
from orion_mcp.core.orchestrator.context_suffixes import (
    apply_chat_user_context_suffixes,
    state_has_catalog_query_summary,
)
from orion_mcp.core.state.models import DataCacheEntry, State


def test_state_has_catalog_query_summary() -> None:
    s = State(
        data_cache={"k": DataCacheEntry(summary="### Resultado de consulta catalogada\n- query_id: x")}
    )
    assert state_has_catalog_query_summary(s) is True
    assert state_has_catalog_query_summary(State()) is False


def test_apply_suffixes_why_and_catalog() -> None:
    base = "### Dados resumidos\nx"
    st = State(
        intent="why_question",
        data_cache={"k": DataCacheEntry(summary="### Resultado de consulta catalogada")},
    )
    out = apply_chat_user_context_suffixes(base, st)
    assert "cautelosa" in out
    assert "SQL" in out or "sql" in out.lower()


def test_apply_suffixes_catalog_full_rows_allows_aggregation() -> None:
    base = "### Dados resumidos\nx"
    st = State(
        data_cache={"k": DataCacheEntry(summary="### Resultado de consulta catalogada")},
    )
    cfg = Settings(tool_llm_catalog_full_rows=True)
    out = apply_chat_user_context_suffixes(base, st, settings=cfg)
    assert "completo" in out.lower()
    assert "agregar" in out.lower() or "Agregar" in out
