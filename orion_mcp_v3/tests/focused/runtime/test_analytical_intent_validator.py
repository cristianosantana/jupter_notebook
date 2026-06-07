from __future__ import annotations

from orion_mcp_v3.broker import ANALYTICS_TEMPLATES
from orion_mcp_v3.broker.query_capability_catalog import build_query_capability_catalog
from orion_mcp_v3.contracts.analytical_intent import (
    AnalyticalDateRange,
    AnalyticalIntentContract,
    AnalyticalIntentType,
    AnalyticalOperation,
    SourcePeriods,
)
from orion_mcp_v3.runtime.analytical_intent_validator import IntentContractValidator
from orion_mcp_v3.runtime.intent_resolver import IntentResolver


def _validator() -> IntentContractValidator:
    return IntentContractValidator(build_query_capability_catalog(ANALYTICS_TEMPLATES))


def test_validator_accepts_comparison_with_two_explicit_periods() -> None:
    heuristic = IntentResolver().resolve("comparar vendas por vendedor")
    contract = AnalyticalIntentContract(
        intent_type=AnalyticalIntentType.COMPARATIVE,
        operation=AnalyticalOperation.DELTA,
        needs_analytics=True,
        needs_memory=True,
        needs_comparison=True,
        template_slug="performance_vendedor",
        metric="sales",
        dimension="seller",
        date_ranges=(
            AnalyticalDateRange("março", "2026-03-01", "2026-03-31"),
            AnalyticalDateRange("abril", "2026-04-01", "2026-04-30"),
        ),
        source_periods=SourcePeriods.EXPLICIT,
        confidence=0.91,
    )

    result = _validator().validate(contract, heuristic_plan=heuristic)

    assert result.accepted is True
    assert result.contract is not None
    assert result.contract.metric == "vendas"
    assert result.contract.dimension == "vendedor"
    assert result.contract.template_slug == "performance_vendedor"
    assert result.cognitive_plan is not None
    assert result.cognitive_plan.intent_type.value == "comparative"
    assert result.cognitive_plan.needs_comparison is True
    assert result.cognitive_plan.time_scope == "2026-03-01/2026-04-30"
    assert result.cognitive_plan.hints["template_slug"] == "performance_vendedor"


def test_validator_rejects_unknown_metric() -> None:
    heuristic = IntentResolver().resolve("qual o lucro por vendedor?")
    contract = AnalyticalIntentContract(
        intent_type=AnalyticalIntentType.ANALYTICAL,
        operation=AnalyticalOperation.LIST,
        needs_analytics=True,
        needs_memory=False,
        needs_comparison=False,
        metric="lucro_liquido",
        dimension="seller",
        confidence=0.9,
    )

    result = _validator().validate(contract, heuristic_plan=heuristic)

    assert result.accepted is False
    assert result.rejected_reason == "unsupported_metric"


def test_validator_rejects_unknown_template() -> None:
    heuristic = IntentResolver().resolve("qual o faturamento por vendedor?")
    contract = AnalyticalIntentContract(
        intent_type=AnalyticalIntentType.ANALYTICAL,
        operation=AnalyticalOperation.RANKING_DESC,
        needs_analytics=True,
        needs_memory=False,
        needs_comparison=False,
        template_slug="visao_inexistente",
        metric="vendas",
        dimension="vendedor",
        confidence=0.9,
    )

    result = _validator().validate(contract, heuristic_plan=heuristic)

    assert result.accepted is False
    assert result.rejected_reason == "unsupported_template"


def test_validator_accepts_supported_collection() -> None:
    heuristic = IntentResolver().resolve("Quero o fechamento gerencial de maio de 2026")
    contract = AnalyticalIntentContract(
        intent_type=AnalyticalIntentType.ANALYTICAL,
        operation=AnalyticalOperation.COLLECTION,
        needs_analytics=True,
        needs_memory=False,
        needs_comparison=False,
        collection_slug="fechamento_gerencial_por_mes",
        date_ranges=(AnalyticalDateRange("maio", "2026-05-01", "2026-05-31"),),
        source_periods=SourcePeriods.EXPLICIT,
        confidence=0.94,
    )

    result = _validator().validate(contract, heuristic_plan=heuristic)

    assert result.accepted is True
    assert result.contract is not None
    assert result.contract.collection_slug == "fechamento_gerencial_por_mes"
    assert result.cognitive_plan is not None
    assert result.cognitive_plan.hints["collection_slug"] == "fechamento_gerencial_por_mes"
    assert result.cognitive_plan.hints["selected_operation"] == "collection"
    assert "template_slug" not in result.cognitive_plan.hints


def test_validator_rejects_unknown_collection() -> None:
    heuristic = IntentResolver().resolve("Quero o fechamento gerencial de maio de 2026")
    contract = AnalyticalIntentContract(
        intent_type=AnalyticalIntentType.ANALYTICAL,
        operation=AnalyticalOperation.COLLECTION,
        needs_analytics=True,
        needs_memory=False,
        needs_comparison=False,
        collection_slug="colecao_inexistente",
        confidence=0.94,
    )

    result = _validator().validate(contract, heuristic_plan=heuristic)

    assert result.accepted is False
    assert result.rejected_reason == "unsupported_collection"


def test_validator_rejects_metric_outside_selected_template() -> None:
    heuristic = IntentResolver().resolve("qual pix por vendedor?")
    contract = AnalyticalIntentContract(
        intent_type=AnalyticalIntentType.ANALYTICAL,
        operation=AnalyticalOperation.RANKING_DESC,
        needs_analytics=True,
        needs_memory=False,
        needs_comparison=False,
        template_slug="performance_vendedor",
        metric="pix",
        dimension="vendedor",
        confidence=0.9,
    )

    result = _validator().validate(contract, heuristic_plan=heuristic)

    assert result.accepted is False
    assert result.rejected_reason == "unsupported_metric"


def test_validator_rejects_comparison_without_period_or_memory_source() -> None:
    heuristic = IntentResolver().resolve("quais vendedores caíram?")
    contract = AnalyticalIntentContract(
        intent_type=AnalyticalIntentType.COMPARATIVE,
        operation=AnalyticalOperation.DELTA,
        needs_analytics=True,
        needs_memory=True,
        needs_comparison=True,
        metric="sales",
        dimension="seller",
        source_periods=SourcePeriods.LAST_TWO_ANALYTICAL_TURNS,
        confidence=0.9,
    )

    result = _validator().validate(
        contract,
        heuristic_plan=heuristic,
        has_analytical_memory=False,
    )

    assert result.accepted is False
    assert result.rejected_reason == "comparison_without_sources"


def test_validator_drops_temporal_entity_filter() -> None:
    heuristic = IntentResolver().resolve("qual a quantidade de PPF em dezembro de 2025?")
    contract = AnalyticalIntentContract(
        intent_type=AnalyticalIntentType.ANALYTICAL,
        operation=AnalyticalOperation.LIST,
        needs_analytics=True,
        needs_memory=False,
        needs_comparison=False,
        template_slug="itens_vendidos",
        metric="quantidade vendida",
        dimension="item",
        entity_filters=(
            {"dimension": "item", "value": "PPF", "match": "exact"},
            {"dimension": "periodo", "value": "2025-12", "match": "exact"},
        ),
        confidence=0.9,
    )

    result = _validator().validate(contract, heuristic_plan=heuristic)

    assert result.accepted is True
    assert result.contract is not None
    assert result.contract.entity_filters == ({"dimension": "item", "value": "PPF", "match": "contains"},)
