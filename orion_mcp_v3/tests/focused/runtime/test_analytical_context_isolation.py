from __future__ import annotations

from orion_mcp_v3.contracts.cognitive_plan import AttentionProfile, CognitivePlan, IntentType
from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.contracts.provenance import CoverageInfo
from orion_mcp_v3.runtime.analytical_context_policy import AnalyticalContextIsolationPolicy
from orion_mcp_v3.runtime.analytical_signature import (
    AnalyticalSignature,
    signature_from_evidence,
)
from orion_mcp_v3.runtime.cognitive_orchestrator import build_fusion_layers


def _plan(
    *,
    intent: IntentType = IntentType.ANALYTICAL,
    analytics: bool = True,
    comparison: bool = False,
) -> CognitivePlan:
    return CognitivePlan(
        intent_type=intent,
        needs_analytics=analytics,
        needs_comparison=comparison,
        metrics=("faturamento",),
        entities=("concessionaria",),
        time_scope="2026-05-01/2026-05-31",
        attention_profile=AttentionProfile.ANALYTICAL if analytics else AttentionProfile.CONVERSATIONAL,
        hints={"date_from": "2026-05-01", "date_to": "2026-05-31"},
    )


def _block(
    text: str,
    *,
    retrieval: str = "episodic",
    signature: AnalyticalSignature | None = None,
    role: ContextRole = ContextRole.ASSISTANT,
) -> ContextBlock:
    metadata: dict[str, object] = {"retrieval": retrieval, "conversation_role": role.value}
    if signature is not None:
        metadata["analytical_signature"] = signature.as_dict()
    return ContextBlock(
        text=text,
        role=role,
        source=ContextSource.MEMORY,
        metadata=metadata,
        relevance_score=0.9,
    )


def test_analytical_fresh_turn_blocks_vector_memory() -> None:
    policy = AnalyticalContextIsolationPolicy()
    decision = policy.decide(_plan())

    assert decision.allow_vector_memory is False
    assert decision.allow_historical_analytics is False


def test_analytical_fresh_turn_removes_old_direct_answers_and_vector_blocks() -> None:
    policy = AnalyticalContextIsolationPolicy()
    plan = _plan()
    blocks = [
        _block("Resposta direta: ticket médio por concessionária: osaka", retrieval="episodic"),
        _block("memória conversacional útil", retrieval="episodic", role=ContextRole.USER),
        _block("faturamento antigo", retrieval="vector"),
    ]

    result = policy.filter_with_trace(blocks, plan)

    assert [b.text for b in result.kept_blocks] == ["memória conversacional útil"]
    assert result.dropped_vector == 1
    assert result.dropped_analytical_memory == 1


def test_comparative_turn_keeps_only_signature_compatible_analytics() -> None:
    policy = AnalyticalContextIsolationPolicy()
    plan = _plan(intent=IntentType.COMPARATIVE, comparison=True)
    current = AnalyticalSignature(
        template_slug="performance_concessionaria",
        measure="vendas",
        dimension="concessionaria",
        date_from="2026-05-01",
        date_to="2026-05-31",
    )
    compatible = _block(
        "Resposta direta: faturamento por concessionária",
        signature=current,
    )
    incompatible = _block(
        "Resposta direta: ticket médio por concessionária",
        signature=AnalyticalSignature(
            template_slug="performance_concessionaria",
            measure="ticket_medio_os",
            dimension="concessionaria",
            date_from="2026-05-01",
            date_to="2026-05-31",
        ),
    )

    result = policy.filter_with_trace([compatible, incompatible], plan, signature=current)

    assert result.kept_blocks == (compatible,)
    assert result.dropped_analytical_memory == 1


def test_comparative_turn_keeps_compatible_analytics_from_contained_periods() -> None:
    policy = AnalyticalContextIsolationPolicy()
    plan = _plan(intent=IntentType.COMPARATIVE, comparison=True)
    current = AnalyticalSignature(
        template_slug="performance_vendedor",
        measure="valor_total",
        dimension="vendedor",
        date_from="2026-03-01",
        date_to="2026-04-30",
    )
    march = _block(
        "Resposta direta: faturamento por vendedor em março",
        signature=AnalyticalSignature(
            template_slug="performance_vendedor",
            measure="valor_total",
            dimension="vendedor",
            date_from="2026-03-01",
            date_to="2026-03-31",
        ),
    )
    april = _block(
        "Resposta direta: faturamento por vendedor em abril",
        signature=AnalyticalSignature(
            template_slug="performance_vendedor",
            measure="valor_total",
            dimension="vendedor",
            date_from="2026-04-01",
            date_to="2026-04-30",
        ),
    )

    result = policy.filter_with_trace([march, april], plan, signature=current)

    assert result.kept_blocks == (march, april)
    assert result.dropped_analytical_memory == 0


def test_comparative_turn_keeps_legacy_analytical_memory_matching_measure_and_dimension() -> None:
    policy = AnalyticalContextIsolationPolicy()
    plan = _plan(intent=IntentType.COMPARATIVE, comparison=True)
    current = AnalyticalSignature(
        template_slug="performance_vendedor",
        measure="valor_total",
        dimension="vendedor",
        date_from="2026-03-01",
        date_to="2026-04-30",
    )
    legacy = _block(
        "Resposta direta: faturamento por vendedor:\n1. ana: R$ 10.000,00",
    )
    unrelated = _block(
        "Resposta direta: ticket médio por concessionária: osaka",
    )

    result = policy.filter_with_trace([legacy, unrelated], plan, signature=current)

    assert result.kept_blocks == (legacy,)
    assert result.dropped_analytical_memory == 1


def test_conversational_turn_preserves_normal_memory() -> None:
    policy = AnalyticalContextIsolationPolicy()
    plan = _plan(intent=IntentType.CONVERSATIONAL, analytics=False)
    blocks = [
        _block("olá, combinamos revisar isso depois", role=ContextRole.USER),
        _block("resposta normal do assistente"),
    ]

    result = policy.filter_with_trace(blocks, plan)

    assert len(result.kept_blocks) == 2
    assert result.dropped_analytical_memory == 0


def test_evidence_block_exports_answer_signature_metadata() -> None:
    plan = _plan()
    evidence = EvidenceBlock(
        summary="Resposta direta: faturamento por concessionária",
        insights={},
        metrics={
            "answer_plan": {
                "template_slug": "performance_concessionaria",
                "measure": "vendas",
                "dimension": "concessionaria",
                "operation": "list",
            },
            "value_key": "vendas",
        },
        confidence=0.9,
        coverage=CoverageInfo(labels={"rows": 2}),
        supporting_data={"direct_answer": {"plan": {"measure": "vendas"}}},
    )

    signature = signature_from_evidence(evidence, fallback=plan)
    layers = build_fusion_layers("quanto faturou?", cognitive_plan=plan, evidence=evidence)
    evidence_block = dict(layers)["evidence"][0]

    assert signature.measure == "vendas"
    assert evidence_block.metadata["answer_plan"] == evidence.metrics["answer_plan"]
    assert evidence_block.metadata["metrics_value_key"] == "vendas"
    assert evidence_block.metadata["analytical_signature"]["measure"] == "vendas"
