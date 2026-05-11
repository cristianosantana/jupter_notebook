"""
Orquestrador cognitivo (§12 ORDEM_IMPLEMENTAÇÃO): fecha o fluxo pós-recuperação até ao prompt.

Encadeia Evidence (como :class:`~ContextBlock`), :class:`~ContextFusion`, :func:`schedule_blocks`,
:func:`allocate` e :func:`render_blocks_to_prompt`. A recuperação paralela (analytics / memória /
essência) permanece à entrada — este módulo assume artefactos já obtidos e formaliza o tail do pipeline.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from orion_mcp_v3.contracts.cognitive_plan import CognitivePlan
from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.contracts.digest import AnalyticalDigest
from orion_mcp_v3.contracts.evidence_block import EvidenceBlock
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
    return ContextBlock(
        text=eb.summary[:8000],
        role=ContextRole.DATA,
        source=ContextSource.BROKER,
        block_id="fusion:evidence",
        metadata={"fusion_kind": "evidence"},
        relevance_score=min(0.95, max(0.0, eb.confidence)),
    )


def _digest_to_context_block(d: AnalyticalDigest) -> ContextBlock:
    conf = d.confidence if d.confidence is not None else 0.6
    return ContextBlock(
        text=d.summary[:8000],
        role=ContextRole.DATA,
        source=ContextSource.BROKER,
        block_id="fusion:map_reduce_digest",
        metadata={"fusion_kind": "digest", "volume": d.volume},
        relevance_score=float(conf),
    )


def build_fusion_layers(
    utterance: str,
    *,
    evidence: EvidenceBlock | None = None,
    digest: AnalyticalDigest | None = None,
    memory_blocks: Sequence[ContextBlock] | None = None,
    essence_blocks: Sequence[ContextBlock] | None = None,
) -> list[tuple[str, list[ContextBlock]]]:
    """Monta camadas para :meth:`ContextFusion.fuse` (utilizador → essência opcional → evidência → digest → memória)."""
    user_cb = ContextBlock(
        utterance,
        ContextRole.USER,
        ContextSource.USER_INPUT,
        block_id="fusion:user_turn",
        relevance_score=1.0,
    )
    layers: list[tuple[str, list[ContextBlock]]] = [("user", [user_cb])]
    mem = list(memory_blocks) if memory_blocks else []
    ess = list(essence_blocks) if essence_blocks else []
    if ess:
        layers.append(("essence", ess))
    if evidence:
        layers.append(("evidence", [_evidence_to_context_block(evidence)]))
    if digest:
        layers.append(("analytics_digest", [_digest_to_context_block(digest)]))
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
        digest: AnalyticalDigest | None = None,
        memory_blocks: Sequence[ContextBlock] | None = None,
        essence_blocks: Sequence[ContextBlock] | None = None,
        max_tokens: int = 4096,
        scheduler_profile: SchedulerProfile | None = None,
    ) -> CognitiveOrchestrationResult:
        plan = cognitive_plan if cognitive_plan is not None else self._resolver.resolve(utterance)
        layers = build_fusion_layers(
            utterance,
            evidence=evidence,
            digest=digest,
            memory_blocks=memory_blocks,
            essence_blocks=essence_blocks,
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
