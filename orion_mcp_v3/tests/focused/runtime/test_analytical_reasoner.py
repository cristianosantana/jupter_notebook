from __future__ import annotations

from orion_mcp_v3.contracts.analytics_outcome import AnalyticsOutcome
from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan, IntentType
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.contracts.evidence_contract import EvidenceContract, EvidenceStatus, PipelineFailure
from orion_mcp_v3.contracts.reasoning_result import AnswerMode
from orion_mcp_v3.runtime.analytical_reasoner import AnalyticalReasoner
from orion_mcp_v3.runtime.provenance import CoverageInfo


def _plan() -> CognitivePlan:
    return CognitivePlan(intent_type=IntentType.ANALYTICAL, needs_analytics=True)


def _evidence_with_contract(contract: EvidenceContract, *, direct: bool = False) -> EvidenceBlock:
    direct_answer = {"plan": {"operation": "list"}, "summary": "Resposta direta:\nA: 10"}
    return EvidenceBlock(
        summary="Resposta direta:\nA: 10" if direct else "Resumo analítico",
        insights={"direct_answer": direct_answer} if direct else {},
        metrics={"evidence_contract": contract.as_dict()},
        confidence=0.8,
        coverage=CoverageInfo(labels={"rows_in": contract.row_count}),
        supporting_data={
            "evidence_contract": contract.as_dict(),
            **({"direct_answer": direct_answer} if direct else {}),
        },
    )


def test_reasoner_uses_literal_mode_for_direct_answer() -> None:
    contract = EvidenceContract.present(row_count=1)
    evidence = _evidence_with_contract(contract, direct=True)

    result = AnalyticalReasoner().reason(
        "liste todos os registros",
        cognitive_plan=_plan(),
        analytics_outcome=AnalyticsOutcome.executed(evidence=evidence, row_count=1, evidence_contract=contract),
    )

    assert result.answer_mode == AnswerMode.LITERAL
    assert any("Resposta direta" in fact for fact in result.facts)
    assert result.evidence_contract.source_priority.value == "direct_answer"


def test_reasoner_keeps_literal_mode_with_structural_insights_for_direct_answer_rows() -> None:
    contract = EvidenceContract.present(row_count=3)
    direct_answer = {
        "plan": {
            "template_slug": "fechamento_faturamento_comissao_concessionaria_periodo",
            "measure": "total_comissao",
            "dimension": "concessionaria",
            "operation": "list",
            "sort": {"field": "total_comissao", "direction": "desc"},
        },
        "summary": "Resposta direta: total comissao por concessionaria",
        "rows": [
            {"concessionaria": "GWM BAMAQ", "total_comissao": "43304.46"},
            {"concessionaria": "SAITAMA - HONDA", "total_comissao": "36755.90"},
            {"concessionaria": "XTREME CAR DETAIL", "total_comissao": "0.00"},
        ],
    }
    evidence = EvidenceBlock(
        summary="Resposta direta: total comissao por concessionaria",
        insights={"direct_answer": direct_answer},
        metrics={"evidence_contract": contract.as_dict()},
        confidence=0.91,
        coverage=CoverageInfo(labels={"rows_in": 3}),
        supporting_data={
            "evidence_contract": contract.as_dict(),
            "direct_answer": direct_answer,
        },
    )

    result = AnalyticalReasoner().reason(
        "qual o total de comissão por concessionária?",
        cognitive_plan=_plan(),
        analytics_outcome=AnalyticsOutcome.executed(evidence=evidence, row_count=3, evidence_contract=contract),
    )

    assert result.answer_mode == AnswerMode.LITERAL
    assert any("3 registro(s)" in fact for fact in result.facts)
    assert any("Total total_comissao" in insight and "80060.36" in insight for insight in result.insights)
    assert any("GWM BAMAQ" in insight and "total_comissao" in insight for insight in result.insights)
    assert any("1 registro(s)" in insight and "zero" in insight for insight in result.insights)
    assert any("ordenada por total_comissao" in insight for insight in result.insights)


def test_reasoner_does_not_sum_literal_rows_without_totalization_intent() -> None:
    contract = EvidenceContract.present(row_count=2)
    direct_answer = {
        "plan": {
            "template_slug": "fechamento_faturamento_comissao_concessionaria_periodo",
            "measure": "total_comissao",
            "dimension": "concessionaria",
            "operation": "list",
            "sort": {"field": "total_comissao", "direction": "desc"},
        },
        "summary": "Resposta direta: comissão por concessionária",
        "rows": [
            {"concessionaria": "GWM BAMAQ", "total_comissao": "43304.46"},
            {"concessionaria": "SAITAMA - HONDA", "total_comissao": "36755.90"},
        ],
    }
    evidence = EvidenceBlock(
        summary="Resposta direta: comissão por concessionária",
        insights={"direct_answer": direct_answer},
        metrics={"evidence_contract": contract.as_dict()},
        confidence=0.91,
        coverage=CoverageInfo(labels={"rows_in": 2}),
        supporting_data={
            "evidence_contract": contract.as_dict(),
            "direct_answer": direct_answer,
        },
    )

    result = AnalyticalReasoner().reason(
        "liste a comissão por concessionária",
        cognitive_plan=_plan(),
        analytics_outcome=AnalyticsOutcome.executed(evidence=evidence, row_count=2, evidence_contract=contract),
    )

    assert result.answer_mode == AnswerMode.LITERAL
    assert not any("Total total_comissao" in insight for insight in result.insights)
    assert any("GWM BAMAQ" in insight and "total_comissao" in insight for insight in result.insights)


def test_reasoner_uses_literal_mode_for_direct_answer_set() -> None:
    contract = EvidenceContract.present(row_count=2)
    direct_answer_set = {
        "collection_slug": "colecao_teste",
        "summary": "Resposta direta composta",
        "answers": [],
    }
    evidence = EvidenceBlock(
        summary="Resposta direta composta",
        insights={"direct_answer_set": direct_answer_set},
        metrics={"evidence_contract": contract.as_dict()},
        confidence=0.8,
        coverage=CoverageInfo(labels={"rows_in": contract.row_count}),
        supporting_data={
            "evidence_contract": contract.as_dict(),
            "direct_answer_set": direct_answer_set,
        },
    )

    result = AnalyticalReasoner().reason(
        "faça o fechamento gerencial",
        cognitive_plan=_plan(),
        analytics_outcome=AnalyticsOutcome.executed(evidence=evidence, row_count=2, evidence_contract=contract),
    )

    assert result.answer_mode == AnswerMode.LITERAL
    assert any("composta" in fact for fact in result.facts)
    assert result.evidence_contract.source_priority.value == "direct_answer"


def test_reasoner_extracts_managerial_closing_executive_facts_from_direct_answer_set() -> None:
    contract = EvidenceContract.present(row_count=5)
    direct_answer_set = {
        "collection_slug": "fechamento_gerencial_por_mes",
        "headline": "Faturamento líquido por forma de pagamento: R$ 1.700,00",
        "summary": "Fechamento executivo",
        "managerial_totals": {
            "financial_net": {
                "label": "Faturamento líquido por forma de pagamento",
                "value": "R$ 1.700,00",
                "source_template": "fechamento_faturamento_tipo_pagamento",
            }
        },
        "executive_sections": [
            {
                "template_slug": "fechamento_faturamento_tipo_pagamento",
                "label": "Faturamento por tipo de pagamento",
                "top": "Cartão de Crédito",
                "top_value": "R$ 1.200,00",
                "share_percent": "70,59%",
                "warnings": [],
            },
            {
                "template_slug": "fechamento_faturamento_comissao_concessionaria_periodo",
                "label": "Faturamento e comissão por concessionária",
                "top": "GWM BAMAQ",
                "top_value": "R$ 90,00",
                "share_percent": "60,00%",
                "warnings": ["1 registro(s) com valor zero"],
            },
        ],
        "data_quality": {"templates_projected": 2, "rows_projected": 5},
        "answers": [],
    }
    evidence = EvidenceBlock(
        summary="Fechamento executivo",
        insights={"direct_answer_set": direct_answer_set},
        metrics={"evidence_contract": contract.as_dict()},
        confidence=0.65,
        coverage=CoverageInfo(labels={"rows_in": contract.row_count}),
        supporting_data={
            "evidence_contract": contract.as_dict(),
            "direct_answer_set": direct_answer_set,
        },
    )

    result = AnalyticalReasoner().reason(
        "faça o fechamento gerencial de maio",
        cognitive_plan=_plan(),
        analytics_outcome=AnalyticsOutcome.executed(evidence=evidence, row_count=5, evidence_contract=contract),
    )

    assert result.answer_mode == AnswerMode.EXECUTIVE
    assert "Faturamento líquido por forma de pagamento: R$ 1.700,00" in result.facts
    assert any("Cartão de Crédito" in insight and "70,59%" in insight for insight in result.insights)
    assert any("valor zero" in risk for risk in result.risks)
    assert any("confiança" in limitation for limitation in result.limitations)


def test_reasoner_distinguishes_pipeline_failure_from_no_data() -> None:
    failure = PipelineFailure(
        stage="intent_interpreter",
        failure_type="no_valid_json",
        impact="interpretação estruturada indisponível",
        analytical_consequence="não é seguro inferir intenção analítica",
        recoverable=True,
    )

    result = AnalyticalReasoner().reason(
        "qual o faturamento?",
        cognitive_plan=_plan(),
        analytics_outcome=AnalyticsOutcome.execution_failure(failure),
    )

    assert result.answer_mode == AnswerMode.OPERATIONAL_FAILURE
    assert result.evidence_contract.status == EvidenceStatus.PIPELINE_FAILURE
    assert "no_valid_json" in " ".join(result.risks)


def test_reasoner_marks_empty_result_without_pipeline_failure() -> None:
    result = AnalyticalReasoner().reason(
        "qual o faturamento?",
        cognitive_plan=_plan(),
        analytics_outcome=AnalyticsOutcome.executed_empty(row_count=0),
    )

    assert result.answer_mode == AnswerMode.ANALYTICAL
    assert result.evidence_contract.status == EvidenceStatus.EMPTY_RESULT
    assert result.risks == ()
    assert any("não retornou linhas" in fact for fact in result.facts)


def test_reasoner_selects_executive_mode_for_summary_requests() -> None:
    contract = EvidenceContract.present(row_count=20)
    evidence = _evidence_with_contract(contract)

    result = AnalyticalReasoner().reason(
        "resuma de forma executiva o faturamento",
        cognitive_plan=_plan(),
        analytics_outcome=AnalyticsOutcome.executed(evidence=evidence, row_count=20, evidence_contract=contract),
    )

    assert result.answer_mode == AnswerMode.EXECUTIVE
    assert result.should_narrate is True
