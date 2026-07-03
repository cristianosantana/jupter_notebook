from __future__ import annotations

from orion_mcp_v3.broker import ANALYTICS_TEMPLATES
from orion_mcp_v3.broker.evidence_aggregator import EvidenceAggregator
from orion_mcp_v3.broker.executor import AnalyticsResult
from orion_mcp_v3.contracts.evidence_contract import EvidenceContract, EvidencePriority, EvidenceStatus
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy, SemanticQueryPlan


def _result(rows):
    plan = SemanticQueryPlan(
        intent_slug="metric.test",
        strategy=RetrievalStrategy.EXACT_LOOKUP,
        hints={},
    )
    return AnalyticsResult(plan=plan, rows=tuple(rows), row_count=len(rows), sql="select 1")


def _template_result(slug, rows, *, collection_slug: str = "fechamento_gerencial_por_mes"):
    plan = SemanticQueryPlan(
        intent_slug=f"template.{slug}",
        strategy=RetrievalStrategy.BROKER_FANOUT,
        hints={
            "template_slug": slug,
            "collection_slug": collection_slug,
            "collection_presentation_mode": "sections",
            "selected_operation": "list",
        },
    )
    return AnalyticsResult(plan=plan, rows=tuple(rows), row_count=len(rows), sql="select 1")


def test_evidence_aggregator_preserves_contract_on_single_result() -> None:
    block = EvidenceAggregator().merge([_result([{"label": "A", "total": 10.0}])])

    contract = EvidenceContract.from_mapping(block.supporting_data.get("evidence_contract"))

    assert contract.status == EvidenceStatus.PRESENT
    assert contract.source_priority == EvidencePriority.FRESH_SQL_EVIDENCE


def test_evidence_aggregator_fanout_marks_aggregated_metrics_priority() -> None:
    block = EvidenceAggregator().merge(
        [
            _result([{"label": "A", "total": 10.0}]),
            _result([{"label": "B", "total": 20.0}]),
        ]
    )

    contract = EvidenceContract.from_mapping(block.supporting_data.get("evidence_contract"))

    assert contract.status == EvidenceStatus.PRESENT
    assert contract.source_priority == EvidencePriority.AGGREGATED_METRICS
    assert contract.row_count == 2


def _comissao_concessionaria_rows(count: int) -> list[dict]:  # type: ignore[type-arg]
    return [
        {
            "periodo": "2026-05",
            "concessionaria": f"Concessionária {index:02d}",
            "total_faturamento": f"{(count - index + 1) * 100:.2f}",
            "total_comissao": f"{(count - index + 1) * 10:.2f}",
        }
        for index in range(1, count + 1)
    ]


def test_evidence_aggregator_collection_fanout_builds_direct_answer_set() -> None:
    block = EvidenceAggregator().merge(
        [
            _template_result(
                "fechamento_producao_servico",
                [{"servico": "Servico A", "quantidade": 2, "total": 100.0, "custo": 10.0}],
            ),
            _template_result(
                "fechamento_producao_produto",
                [{"produto": "Produto B", "quantidade": 1, "total": 50.0}],
            ),
        ],
        templates=ANALYTICS_TEMPLATES,
        query_text="Resumo gerencial mensal",
    )

    direct_set = block.supporting_data.get("direct_answer_set")
    contract = EvidenceContract.from_mapping(block.supporting_data.get("evidence_contract"))

    assert isinstance(direct_set, dict)
    assert direct_set["collection_slug"] == "fechamento_gerencial_por_mes"
    assert len(direct_set["answers"]) == 2
    assert "fechamento_producao_servico" in block.summary
    assert "fechamento_producao_produto" in block.summary
    assert contract.source_priority == EvidencePriority.DIRECT_ANSWER


def test_evidence_aggregator_collection_fanout_embeds_full_section_detail_when_truncated() -> None:
    block = EvidenceAggregator().merge(
        [
            _template_result(
                "fechamento_faturamento_comissao_concessionaria_periodo",
                _comissao_concessionaria_rows(31),
            ),
        ],
        templates=ANALYTICS_TEMPLATES,
        query_text="Faça o fechamento gerencial de maio de 2026",
    )

    direct_set = block.supporting_data.get("direct_answer_set")
    assert isinstance(direct_set, dict)
    assert "Omitidas" in str(direct_set.get("section_detail") or "")
    full_section_detail = direct_set.get("full_section_detail")
    assert isinstance(full_section_detail, str)
    assert "Omitidas" not in full_section_detail
    assert "11. Concessionária 11:" in full_section_detail
    assert "31. Concessionária 31:" in full_section_detail
