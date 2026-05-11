from orion_mcp.core.state.intent_heuristic import (
    apply_task_heuristic_profile,
    format_task_profile_for_context,
)
from orion_mcp.core.state.models import DataCacheEntry, State


def test_apply_task_profile_why_question_conservative() -> None:
    s0 = State(intent="why_question")
    s = apply_task_heuristic_profile(s0, "Porquê caiu a conversão?")
    tp = s.entities.get("task_profile")
    assert isinstance(tp, dict)
    assert tp["risk_posture"] == "conservador"
    assert tp["data_status"] == "no_data"
    assert tp["analytics_catalog_query"] is False


def test_apply_task_profile_with_cache_normal_risk() -> None:
    s0 = State(
        intent="general",
        data_cache={"k": DataCacheEntry(summary="rows=10")},
    )
    s = apply_task_heuristic_profile(s0, "Olá")
    tp = s.entities["task_profile"]
    assert tp["data_status"] == "has_cache"
    assert tp["risk_posture"] == "normal"


def test_apply_task_profile_degraded_from_summary() -> None:
    s0 = State(
        intent="general",
        data_cache={"k": DataCacheEntry(summary="mcp_degraded: timeout")},
    )
    s = apply_task_heuristic_profile(s0, "Resumo")
    tp = s.entities["task_profile"]
    assert tp["data_status"] == "degraded"
    assert tp["risk_posture"] == "conservador"


def test_apply_task_profile_query_id_catalog() -> None:
    s0 = State(intent="general", flags={"domain_query_id": "sales_daily"})
    s = apply_task_heuristic_profile(s0, "Mostra totais")
    tp = s.entities["task_profile"]
    assert tp["analytics_catalog_query"] is True
    assert "consulta_catalogada" in tp["summary_for_llm"] or "sim" in tp["summary_for_llm"]


def test_apply_task_profile_pragmatic_keywords() -> None:
    s0 = State(intent="general")
    s = apply_task_heuristic_profile(s0, "Lista os top 5 produtos")
    assert s.entities["task_profile"]["pragmatic_brevity_hint"] is True


def test_format_task_profile_missing() -> None:
    s = State()
    assert format_task_profile_for_context(s) == "(não aplicável)"


def test_format_task_profile_present() -> None:
    s = apply_task_heuristic_profile(State(intent="format_only"), "Em tabela")
    text = format_task_profile_for_context(s)
    assert "postura_risco" in text or "resumo:" in text
    assert "estruturada" in text or "Formatar" in text
