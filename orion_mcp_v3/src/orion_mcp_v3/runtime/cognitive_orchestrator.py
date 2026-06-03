"""
Orquestrador cognitivo (§12 ORDEM_IMPLEMENTAÇÃO): fecha o fluxo pós-recuperação até ao prompt.

Encadeia Evidence (como :class:`~ContextBlock`), :class:`~ContextFusion`, :func:`schedule_blocks`,
:func:`allocate` e :func:`render_blocks_to_prompt`. A recuperação paralela (analytics / memória /
essência) permanece à entrada — este módulo assume artefactos já obtidos e formaliza o tail do pipeline.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass

from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan
from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.contracts.digest import AnalyticalDigest
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
from orion_mcp_v3.contracts.reasoning_result import AnalyticalReasoningResult
from orion_mcp_v3.runtime.analytical_system_prompt import build_analytical_system_block
from orion_mcp_v3.runtime.analytical_signature import signature_from_evidence
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy
from orion_mcp_v3.runtime.budget_allocator import allocate
from orion_mcp_v3.runtime.context_fusion import ContextFusion, ContextFusionResult
from orion_mcp_v3.runtime.intent_resolver import IntentResolver
from orion_mcp_v3.runtime.prompt_render import render_blocks_to_prompt
from orion_mcp_v3.runtime.scheduler import SchedulerProfile, schedule_blocks, scheduler_profile_from_attention


@dataclass(frozen=True, slots=True)
class CognitiveOrchestrationResult:
    """Resultado do tail: plano cognitivo + fusão + blocos ordenados/orçados + texto de prompt."""

    cognitive_plan: CognitivePlan
    fusion: ContextFusionResult
    scheduled_blocks: tuple[ContextBlock, ...]
    packed_blocks: tuple[ContextBlock, ...]
    prompt_text: str


def _evidence_to_context_block(eb: EvidenceBlock) -> ContextBlock:
    signature = signature_from_evidence(eb)
    md: dict[str, object] = {
        "fusion_kind": "evidence",
        "evidence_confidence": eb.confidence,
        "coverage_labels": list(eb.coverage.labels),
        "provenance_count": len(eb.provenance),
        "analytical_signature": signature.as_dict(),
    }
    direct_answer = eb.supporting_data.get("direct_answer") if eb.supporting_data else None
    direct_answer_set = eb.supporting_data.get("direct_answer_set") if eb.supporting_data else None
    answer_plan = eb.metrics.get("answer_plan") if eb.metrics else None
    metrics_value_key = eb.metrics.get("value_key") if eb.metrics else None
    if answer_plan is not None:
        md["answer_plan"] = answer_plan
    if direct_answer is not None:
        md["direct_answer"] = direct_answer
    if direct_answer_set is not None:
        md["direct_answer_set"] = direct_answer_set
    if metrics_value_key is not None:
        md["metrics_value_key"] = metrics_value_key
    if eb.provenance:
        md["provenance_sources"] = [a.source for a in eb.provenance[:8]]
    return ContextBlock(
        text=eb.summary[:8000],
        role=ContextRole.DATA,
        source=ContextSource.BROKER,
        block_id="fusion:evidence",
        metadata=md,
        relevance_score=min(0.95, max(0.0, eb.confidence)),
    )


def _digest_to_context_block(d: AnalyticalDigest) -> ContextBlock:
    conf = d.confidence if d.confidence is not None else 0.6
    md: dict[str, object] = {"fusion_kind": "digest", "volume": d.volume}
    if d.coverage is not None:
        md["coverage_labels"] = list(d.coverage.labels)
    return ContextBlock(
        text=d.summary[:8000],
        role=ContextRole.DATA,
        source=ContextSource.BROKER,
        block_id="fusion:map_reduce_digest",
        metadata=md,
        relevance_score=float(conf),
    )


def _reasoning_to_context_block(reasoning: AnalyticalReasoningResult) -> ContextBlock:
    payload = reasoning.as_dict()
    return ContextBlock(
        text=json.dumps(payload, ensure_ascii=False, default=str),
        role=ContextRole.DATA,
        source=ContextSource.SYSTEM,
        block_id="fusion:reasoning_result",
        metadata={
            "fusion_kind": "reasoning_result",
            "answer_mode": payload.get("answer_mode"),
            "should_narrate": payload.get("should_narrate"),
            "evidence_status": (payload.get("evidence_contract") or {}).get("status"),
            "evidence_contract": payload.get("evidence_contract"),
        },
        relevance_score=1.0,
    )


def build_fusion_layers(
    utterance: str,
    *,
    cognitive_plan: CognitivePlan | None = None,
    evidence: EvidenceBlock | None = None,
    reasoning_result: AnalyticalReasoningResult | None = None,
    digest: AnalyticalDigest | None = None,
    memory_blocks: Sequence[ContextBlock] | None = None,
    essence_blocks: Sequence[ContextBlock] | None = None,
    period_label: str | None = None,
) -> list[tuple[str, list[ContextBlock]]]:
    """Monta camadas para :meth:`ContextFusion.fuse`.

    Ordem: system → user → evidência → digest → essência opcional → memória.
    O bloco SYSTEM é injetado somente quando ``cognitive_plan`` é fornecido, preservando
    compatibilidade para chamadas diretas de ``build_fusion_layers`` sem plano.
    """
    layers: list[tuple[str, list[ContextBlock]]] = []
    if cognitive_plan is not None:
        layers.append(
            (
                "system",
                [
                    build_analytical_system_block(
                        cognitive_plan,
                        evidence=evidence,
                        period_label=period_label,
                    )
                ],
            )
        )

    user_cb = ContextBlock(
        utterance,
        ContextRole.USER,
        ContextSource.USER_INPUT,
        block_id="fusion:user_turn",
        relevance_score=1.0,
    )
    layers.append(("user", [user_cb]))
    mem = list(memory_blocks) if memory_blocks else []
    ess = list(essence_blocks) if essence_blocks else []
    if evidence:
        layers.append(("evidence", [_evidence_to_context_block(evidence)]))
    if reasoning_result:
        layers.append(("reasoning", [_reasoning_to_context_block(reasoning_result)]))
    if digest:
        layers.append(("analytics_digest", [_digest_to_context_block(digest)]))
    if ess:
        layers.append(("essence", ess))
    if mem:
        layers.append(("memory", mem))
    return layers


class CognitiveOrchestrator:
    """
    ``IntentResolver → CognitivePlan`` opcional; depois fusão → scheduler → allocator → prompt.

    Use :meth:`finalize_prompt` quando já tiver artefactos de retrieval; passe ``cognitive_plan``
    para evitar segundo resolve na mesma volta.
    """

    def __init__(self, *, intent_resolver: IntentResolver | None = None) -> None:
        self._resolver = intent_resolver or IntentResolver()

    def finalize_prompt(
        self,
        utterance: str,
        *,
        policy: AttentionPolicy,
        cognitive_plan: CognitivePlan | None = None,
        evidence: EvidenceBlock | None = None,
        reasoning_result: AnalyticalReasoningResult | None = None,
        digest: AnalyticalDigest | None = None,
        memory_blocks: Sequence[ContextBlock] | None = None,
        essence_blocks: Sequence[ContextBlock] | None = None,
        max_tokens: int = 4096,
        scheduler_profile: SchedulerProfile | None = None,
        period_label: str | None = None,
    ) -> CognitiveOrchestrationResult:
        plan = cognitive_plan if cognitive_plan is not None else self._resolver.resolve(utterance)
        layers = build_fusion_layers(
            utterance,
            cognitive_plan=plan,
            evidence=evidence,
            reasoning_result=reasoning_result,
            digest=digest,
            memory_blocks=memory_blocks,
            essence_blocks=essence_blocks,
            period_label=period_label,
        )
        fusion = ContextFusion().fuse(layers, policy=policy)
        profile = scheduler_profile or scheduler_profile_from_attention(policy)
        scheduled = schedule_blocks(list(fusion.blocks), profile, policy=policy)
        packed = allocate(scheduled, max_tokens, policy=policy).fitted_blocks
        prompt = render_blocks_to_prompt(packed)
        return CognitiveOrchestrationResult(
            cognitive_plan=plan,
            fusion=fusion,
            scheduled_blocks=tuple(scheduled),
            packed_blocks=packed,
            prompt_text=prompt,
        )
