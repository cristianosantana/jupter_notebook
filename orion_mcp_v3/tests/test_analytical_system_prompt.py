"""Testes do bloco SYSTEM analítico injetado no CognitiveOrchestrator."""

from __future__ import annotations

from orion_mcp_v3.contracts.cognitive_plan import AttentionProfile, CognitivePlan, IntentType
from orion_mcp_v3.contracts.context_block import ContextRole, ContextSource
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.contracts.provenance import CoverageInfo
from orion_mcp_v3.runtime.analytical_system_prompt import (
    _resolve_period,
    build_analytical_system_block,
)
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy
from orion_mcp_v3.runtime.cognitive_orchestrator import CognitiveOrchestrator, build_fusion_layers


def _plan(
    *,
    intent: IntentType = IntentType.ANALYTICAL,
    needs_analytics: bool = True,
    time_scope: str | None = None,
    hints: dict | None = None,
) -> CognitivePlan:
    return CognitivePlan(
        intent_type=intent,
        needs_analytics=needs_analytics,
        confidence=0.8,
        metrics=("revenue",),
        attention_profile=AttentionProfile.ANALYTICAL,
        time_scope=time_scope,
        hints=hints or {},
    )


def _evidence(*, confidence: float = 0.8) -> EvidenceBlock:
    return EvidenceBlock(
        summary="Forma de pagamento dominante: pix. Total recebido: R$ 10.000,00.",
        insights={},
        metrics={"n": 10},
        confidence=confidence,
        coverage=CoverageInfo(
            labels={"templates_ok": 3, "templates_total": 4},
            notes="evidence_builder.sql_rows",
        ),
    )


def test_system_block_has_system_role_source_and_fixed_id() -> None:
    block = build_analytical_system_block(_plan())
    assert block.role == ContextRole.SYSTEM
    assert block.source == ContextSource.SYSTEM
    assert block.block_id == "system:analytical_prompt"
    assert block.relevance_score == 1.0


def test_analytical_prompt_contains_identity_structure_and_anti_hallucination() -> None:
    block = build_analytical_system_block(_plan())
    assert "Orion" in block.text
    assert "Visão geral" in block.text
    assert "Destaques" in block.text
    assert "Conclusão acionável" in block.text
    assert "O QUE NUNCA FAZER" in block.text


def test_conversational_intent_uses_concise_structure_without_analytics_sections() -> None:
    block = build_analytical_system_block(
        _plan(intent=IntentType.CONVERSATIONAL, needs_analytics=False)
    )
    assert "Responda de forma natural e concisa" in block.text
    assert "Visão geral" not in block.text
    assert "O QUE NUNCA FAZER" in block.text


def test_period_label_has_priority_and_goes_to_metadata() -> None:
    block = build_analytical_system_block(
        _plan(time_scope="2026-01-01/2026-04-30"),
        period_label="jan-abr/2026",
    )
    assert "jan-abr/2026" in block.text
    assert block.metadata["period"] == "jan-abr/2026"


def test_resolve_period_uses_plan_hints_before_raw_time_scope() -> None:
    plan = _plan(
        time_scope="2026-01-01/2026-04-30",
        hints={"date_from": "2026-01-01", "date_to": "2026-04-30"},
    )
    assert _resolve_period(None, plan, None) == "2026-01-01 a 2026-04-30"


def test_low_confidence_evidence_adds_warning_and_coverage_note() -> None:
    block = build_analytical_system_block(_plan(), evidence=_evidence(confidence=0.45))
    assert "confiança da evidência é baixa" in block.text
    assert "3/4 templates executados com sucesso" in block.text
    assert block.metadata["evidence_confidence"] == 0.45


def test_build_fusion_layers_without_cognitive_plan_preserves_no_system_layer() -> None:
    layers = build_fusion_layers("pergunta simples", cognitive_plan=None)
    assert [name for name, _ in layers] == ["user"]


def test_finalize_prompt_injects_system_before_user() -> None:
    result = CognitiveOrchestrator().finalize_prompt(
        "faça uma análise do faturamento de janeiro a abril de 2026",
        policy=AttentionPolicy.ANALYTICAL,
        cognitive_plan=_plan(hints={"date_from": "2026-01-01", "date_to": "2026-04-30"}),
        period_label="jan-abr/2026",
        max_tokens=20_000,
    )
    sys_pos = result.prompt_text.find("[SYSTEM]")
    user_pos = result.prompt_text.find("[USER]")
    assert sys_pos != -1
    assert user_pos != -1
    assert sys_pos < user_pos
    assert "Orion" in result.prompt_text
    assert "jan-abr/2026" in result.prompt_text
    assert any(b.block_id == "system:analytical_prompt" for b in result.packed_blocks)
