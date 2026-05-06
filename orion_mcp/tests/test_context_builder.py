from orion_mcp.core.config.settings import Settings
from orion_mcp.core.context.context_builder import build_context
from orion_mcp.core.state.models import DataCacheEntry, State


def test_build_context_no_history_dump() -> None:
    settings = Settings()
    s = State(
        intent="general",
        current_metric="demo",
        data_cache={"abc": DataCacheEntry(summary="metric=1")},
        insights=["i1"],
        short_memory="prev",
    )
    res = build_context(s, "What is X?", settings)
    assert "What is X?" in res.text
    assert "role=user" not in res.text.lower()
    assert "### Dados resumidos" in res.text
    assert "### Perfil da tarefa (heurística)" in res.text
    assert res.text.index("### Pergunta atual") < res.text.index("### Dados resumidos")


def test_build_context_respects_token_budget() -> None:
    settings = Settings(context_max_tokens=200, context_section_budget_tokens=250)
    big = "word " * 2000
    s = State(short_memory=big, data_cache={"k": DataCacheEntry(summary=big)})
    res = build_context(s, "q", settings)
    assert len(res.text) < len(big) * 3
    assert res.context_truncated is True


def test_build_context_preserves_question_with_large_data_cache() -> None:
    """«Pergunta actual» vem antes de «Dados resumidos» e não é omitida pelo orçamento."""
    settings = Settings(
        context_max_tokens=380,
        llm_max_prompt_tokens=380,
        context_section_budget_tokens=380,
    )
    big = "metric_row " * 400
    s = State(
        intent="general",
        current_metric="x",
        data_cache={f"k{i}": DataCacheEntry(summary=big) for i in range(30)},
        short_memory="",
        insights=[],
    )
    marker = "PERGUNTA_MARCADOR_UNICA_XY42"
    res = build_context(s, marker, settings)
    assert marker in res.text
    assert res.text.index("### Pergunta atual") < res.text.index("### Dados resumidos")
    assert res.context_truncated is True
