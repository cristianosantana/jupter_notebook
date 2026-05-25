from __future__ import annotations

from orion_mcp_v3.broker import ANALYTICS_TEMPLATES, AnalyticsResult, EvidenceAggregator, QueryExpander
from orion_mcp_v3.config.allowlists import ANALYTICS_ALLOWLIST
from orion_mcp_v3.config.settings import get_settings_uncached
from orion_mcp_v3.contracts.analytical_intent import (
    AnalyticalIntentContract,
    AnalyticalIntentType,
    AnalyticalOperation,
)
from orion_mcp_v3.contracts.cognitive_plan import AttentionProfile, CognitivePlan, IntentType
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy, SemanticQueryPlan
from orion_mcp_v3.runtime.analytical_intent_validator import IntentContractValidator
from orion_mcp_v3.runtime.intent_resolver import IntentResolver
from orion_mcp_v3.broker.query_capability_catalog import build_query_capability_catalog


def _analytical_plan(**overrides) -> CognitivePlan:  # type: ignore[no-untyped-def]
    defaults = {
        "intent_type": IntentType.ANALYTICAL,
        "needs_analytics": True,
        "confidence": 0.91,
        "retrieval_strategy": RetrievalStrategy.BROKER_FANOUT,
        "attention_profile": AttentionProfile.ANALYTICAL,
    }
    defaults.update(overrides)
    return CognitivePlan(**defaults)


def _result(slug: str, rows: list[dict]) -> AnalyticsResult:  # type: ignore[type-arg]
    return AnalyticsResult(
        plan=SemanticQueryPlan(
            intent_slug=f"template.{slug}",
            strategy=RetrievalStrategy.BROKER_FANOUT,
            hints={"template_slug": slug, "template_params": {}},
        ),
        sql="SELECT ...",
        rows=rows,
        row_count=len(rows),
    )


def _selected_result(
    *,
    metric: str,
    operation: str,
    rows: list[dict],  # type: ignore[type-arg]
    dimension: str = "concessionaria",
) -> AnalyticsResult:
    return AnalyticsResult(
        plan=SemanticQueryPlan(
            intent_slug="template.performance_concessionaria",
            strategy=RetrievalStrategy.BROKER_FANOUT,
            hints={
                "template_slug": "performance_concessionaria",
                "template_params": {},
                "selected_metric": metric,
                "selected_dimension": dimension,
                "selected_operation": operation,
            },
        ),
        sql="SELECT ...",
        rows=rows,
        row_count=len(rows),
    )


def test_new_question_flows_through_existing_semantic_view() -> None:
    cp = _analytical_plan(
        metrics=("recebido",),
        entities=("concessionaria",),
        hints={
            "template_slug": "performance_concessionaria",
            "intent_contract": {
                "template_slug": "performance_concessionaria",
                "metric": "recebido",
                "dimension": "concessionaria",
                "operation": "ranking_desc",
            },
        },
    )

    plans = QueryExpander(registry=ANALYTICS_TEMPLATES).expand(
        cp,
        ANALYTICS_ALLOWLIST,
        query_text="qual loja puxou mais recebimento neste período?",
    )

    assert len(plans) == 1
    assert plans[0].hints["template_slug"] == "performance_concessionaria"
    assert plans[0].hints["selected_metric"] == "recebido"
    assert plans[0].hints["semantic_reason"] == "validated_intent_contract"


def test_evidence_preserves_validated_list_metric_from_semantic_plan() -> None:
    rows = [
        {"concessionaria": "porsche", "vendas": "167440.00", "recebido": "165370.00"},
        {"concessionaria": "gwm bamaq", "vendas": "159190.00", "recebido": "147750.00"},
    ]

    evidence = EvidenceAggregator().merge(
        [_selected_result(metric="vendas", operation="list", rows=rows)],
        templates=ANALYTICS_TEMPLATES,
        query_text="Quanto cada concessionária faturou de março de 2026?",
    )

    assert evidence.metrics["answer_plan"]["measure"] == "vendas"
    assert evidence.metrics["answer_plan"]["operation"] == "list"
    assert "vendas por concessionária" in evidence.summary
    assert "porsche: R$ 167.440,00" in evidence.summary
    assert "recebido por concessionária" not in evidence.summary


def test_evidence_series_uses_selected_metric_for_complementary_summary() -> None:
    rows = [
        {"concessionaria": "porsche", "vendas": "167440.00", "recebido": "165370.00"},
        {"concessionaria": "gwm bamaq", "vendas": "159190.00", "recebido": "147750.00"},
    ]

    evidence = EvidenceAggregator().merge(
        [_selected_result(metric="recebido", operation="list", rows=rows)],
        templates=ANALYTICS_TEMPLATES,
        query_text="gostaria de saber o recebimento de todas as concessionarias nesse periodo",
    )

    assert evidence.metrics["value_key"] == "recebido"
    assert "Ranking por `recebido`" in evidence.summary
    assert "Ranking por `vendas`" not in evidence.summary


def test_below_average_question_lists_all_below_average_rows() -> None:
    rows = [
        {"concessionaria": "porsche", "vendas": "2000.00"},
        {"concessionaria": "gwm bamaq", "vendas": "600.00"},
        {"concessionaria": "euroville volvo jf", "vendas": "100.00"},
    ]

    evidence = EvidenceAggregator().merge(
        [_selected_result(metric="vendas", operation="ranking_asc", rows=rows)],
        templates=ANALYTICS_TEMPLATES,
        query_text="quais concessionarias merecem atenção por causa de vendas abaixo da média?",
    )

    assert evidence.metrics["answer_plan"]["operation"] == "below_average"
    assert "abaixo da média" in evidence.summary
    assert "gwm bamaq" in evidence.summary
    assert "euroville volvo jf" in evidence.summary
    assert "menor vendas por concessionária" not in evidence.summary


def test_contract_validator_blocks_operation_outside_selected_view() -> None:
    heuristic = IntentResolver().resolve("resuma faturamento por vendedor")
    contract = AnalyticalIntentContract(
        intent_type=AnalyticalIntentType.ANALYTICAL,
        operation=AnalyticalOperation.SUMMARY,
        needs_analytics=True,
        needs_memory=False,
        needs_comparison=False,
        template_slug="performance_vendedor",
        metric="vendas",
        dimension="vendedor",
        confidence=0.9,
    )
    validator = IntentContractValidator(build_query_capability_catalog(ANALYTICS_TEMPLATES))

    result = validator.validate(contract, heuristic_plan=heuristic)

    assert result.accepted is False
    assert result.rejected_reason == "unsupported_operation"


def test_embeddings_off_keeps_analytics_independent_from_vector_layer() -> None:
    settings = get_settings_uncached(embedding_mode="off", embedding_enabled=False, llm_api_key="")

    assert settings.effective_embedding_mode == "off"
    assert settings.embedding_active is False
    assert settings.embedding_should_index is False
    assert settings.embedding_should_retrieve is False


def test_evidence_first_payload_reaches_narrator_boundary() -> None:
    rows = [
        {"concessionaria": "osaka", "vendas": "187547.00", "quantidade_os": 176},
        {"concessionaria": "strada jeep", "vendas": "112575.00", "quantidade_os": 261},
    ]

    evidence = EvidenceAggregator().merge(
        [_result("performance_concessionaria", rows)],
        templates=ANALYTICS_TEMPLATES,
        query_text="qual concessionária vendeu mais?",
    )

    assert evidence.summary.startswith("Resposta direta")
    assert evidence.metrics["answer_plan"]["template_slug"] == "performance_concessionaria"
    assert evidence.supporting_data["direct_answer"]["top"]["concessionaria"] == "osaka"
