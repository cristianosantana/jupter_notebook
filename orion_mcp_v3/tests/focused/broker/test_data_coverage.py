from __future__ import annotations

from orion_mcp_v3.broker import ANALYTICS_TEMPLATES, AnalyticsResult, EvidenceAggregator, EvidenceBuilder
from orion_mcp_v3.broker.aggregators import _parse_time, time_series
from orion_mcp_v3.contracts.evidence_contract import EvidenceContract, EvidencePriority
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy, SemanticQueryPlan


def test_parse_time_accepts_yyyy_mm_periodo() -> None:
    parsed = _parse_time("2024-11")
    assert parsed is not None
    assert parsed.year == 2024
    assert parsed.month == 11
    assert parsed.day == 1


def test_time_series_aggregates_rows_with_yyyy_mm_periodo() -> None:
    rows = [
        {"periodo": "2024-11", "caixa_tipo": "Cartão de Crédito", "total_liquido": "100.00"},
        {"periodo": "2024-11", "caixa_tipo": "PIX", "total_liquido": "50.00"},
    ]
    periods = time_series(rows, time_key="periodo", value_key="total_liquido", grain="month")
    assert len(periods) == 1
    assert periods[0]["period"] == "2024-11"
    assert periods[0]["total"] == 150.0


def test_evidence_builder_coverage_uses_temporal_component_for_yyyy_mm() -> None:
    rows = [
        {"periodo": "2024-11", "caixa_tipo": "Cartão de Crédito", "total_liquido": "100.00"},
        {"periodo": "2024-11", "caixa_tipo": "PIX", "total_liquido": "50.00"},
    ]
    block = EvidenceBuilder().build(
        rows,
        value_key="total_liquido",
        label_key="caixa_tipo",
        time_key="periodo",
        grain="month",
    )
    contract = EvidenceContract.from_mapping(block.supporting_data.get("evidence_contract"))
    coverage = contract.operational_confidence.data_coverage
    assert coverage > 0.65
    assert coverage < 1.0


def _tipo_pagamento_result(rows: list[dict]) -> AnalyticsResult:
    return AnalyticsResult(
        plan=SemanticQueryPlan(
            intent_slug="template.fechamento_faturamento_tipo_pagamento",
            strategy=RetrievalStrategy.BROKER_FANOUT,
            hints={
                "template_slug": "fechamento_faturamento_tipo_pagamento",
                "template_params": {},
                "selected_metric": "total_liquido",
                "selected_dimension": "caixa_tipo",
                "selected_operation": "ranking_desc",
                "result_scope": {"mode": "all", "limit": None},
                "sort": {"field": "total_liquido", "direction": "desc"},
            },
        ),
        sql="SELECT ...",
        rows=rows,
        row_count=len(rows),
    )


def test_projected_direct_answer_sets_full_data_coverage() -> None:
    rows = [
        {
            "caixa_tipo_id": 2,
            "caixa_tipo": "Cartão de Crédito",
            "periodo": "2024-11",
            "total_pagamentos": "1477061.82",
            "total_estornos": "0.00",
            "total_liquido": "1477061.82",
        },
        {
            "caixa_tipo_id": 5,
            "caixa_tipo": "PIX",
            "periodo": "2024-11",
            "total_pagamentos": "321325.50",
            "total_estornos": "0.00",
            "total_liquido": "321325.50",
        },
    ]
    block = EvidenceAggregator().merge(
        [_tipo_pagamento_result(rows)],
        templates=ANALYTICS_TEMPLATES,
        query_text="Qual forma de pagamento domina o faturamento em novembro de 2024?",
    )
    contract = EvidenceContract.from_mapping(block.supporting_data.get("evidence_contract"))
    assert contract.source_priority == EvidencePriority.DIRECT_ANSWER
    assert contract.full_dataset_available is True
    assert contract.operational_confidence.data_coverage == 1.0
