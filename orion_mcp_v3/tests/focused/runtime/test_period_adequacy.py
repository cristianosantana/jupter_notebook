from __future__ import annotations

import pytest

from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan, IntentType
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.runtime.provenance import CoverageInfo
from orion_mcp_v3.runtime.period_adequacy import resolve_period_adequacy


def test_period_gate_inherits_period_from_last_direct_answer() -> None:
    plan = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        metrics=("ticket_medio_item",),
        entities=("item",),
    )
    evidence = EvidenceBlock(
        summary="Resposta direta",
        insights={},
        metrics={},
        confidence=0.9,
        coverage=CoverageInfo(labels={"rows_in": 1}),
        supporting_data={
            "direct_answer": {
                "rows": [{"periodo": "2026-05", "item": "ppf", "ticket_medio_item": "1000.00"}]
            }
        },
    )

    decision = resolve_period_adequacy(
        "Qual o ticket médio por item do período?",
        plan,
        last_evidence=evidence,
    )

    assert decision.should_block is False
    assert decision.plan.time_scope == "2026-05-01/2026-05-31"
    assert decision.plan.hints["period_source"] == "inherited_last_analytical_evidence"


def test_period_gate_inherits_same_period_phrase_from_last_direct_answer() -> None:
    plan = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        metrics=("total_comissao",),
        entities=("concessionaria",),
    )
    evidence = EvidenceBlock(
        summary="Resposta direta",
        insights={},
        metrics={},
        confidence=0.9,
        coverage=CoverageInfo(labels={"rows_in": 1}),
        supporting_data={
            "direct_answer": {
                "rows": [
                    {
                        "periodo": "2026-04",
                        "concessionaria": "GWM BAMAQ",
                        "total_comissao": "43304.46",
                    }
                ]
            }
        },
    )

    decision = resolve_period_adequacy(
        "Qual o total de comissão por concessionária do mesmo período?",
        plan,
        last_evidence=evidence,
    )

    assert decision.should_block is False
    assert decision.plan.time_scope == "2026-04-01/2026-04-30"
    assert decision.inherited_from == "last_analytical_evidence"


@pytest.mark.parametrize(
    "message",
    (
        "Qual o total de comissão por concessionária nessa competência?",
        "Repita a análise na mesma janela.",
        "Liste novamente para o recorte citado.",
        "Qual foi o resultado no intervalo analisado?",
    ),
)
def test_period_gate_inherits_semantic_temporal_anaphora(message: str) -> None:
    plan = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        metrics=("total_comissao",),
        entities=("concessionaria",),
    )
    evidence = EvidenceBlock(
        summary="Resposta direta",
        insights={},
        metrics={},
        confidence=0.9,
        coverage=CoverageInfo(labels={"rows_in": 1}),
        supporting_data={
            "direct_answer": {
                "rows": [{"periodo": "2026-04", "concessionaria": "GWM BAMAQ"}]
            }
        },
    )

    decision = resolve_period_adequacy(message, plan, last_evidence=evidence)

    assert decision.should_block is False
    assert decision.plan.time_scope == "2026-04-01/2026-04-30"
    assert decision.inherited_from == "last_analytical_evidence"


def test_period_gate_blocks_anaphoric_period_without_context() -> None:
    plan = CognitivePlan(
        intent_type=IntentType.ANALYTICAL,
        needs_analytics=True,
        metrics=("ticket_medio_item",),
        entities=("item",),
    )

    decision = resolve_period_adequacy(
        "Qual o ticket médio por item do período?",
        plan,
        last_evidence=None,
    )

    assert decision.should_block is True
    assert decision.blocked_reason == "missing_period_context"
