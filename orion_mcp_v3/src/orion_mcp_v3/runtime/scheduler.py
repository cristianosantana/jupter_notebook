"""
Scheduler cognitivo (Fase 4.2): score real com relevance, confidence, coverage,
importance, information_density + slot competition DATA vs MEMORY.
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.runtime.attention_policy import (
    AttentionPolicy,
    AttentionPolicyDefinition,
    policy_definition,
)


class SchedulerProfile(Enum):
    """Perfis de competição entre blocos — pesos distintos sobre o mesmo score base."""

    ANALYTICAL = "analytical"
    CONVERSATIONAL = "conversational"
    HYBRID = "hybrid"


_POLICY_TO_SCHEDULER: dict[AttentionPolicy, SchedulerProfile] = {
    AttentionPolicy.ANALYTICAL: SchedulerProfile.ANALYTICAL,
    AttentionPolicy.BALANCED: SchedulerProfile.CONVERSATIONAL,
    AttentionPolicy.MEMORY_FOCUSED: SchedulerProfile.CONVERSATIONAL,
    AttentionPolicy.CONVERSATIONAL: SchedulerProfile.CONVERSATIONAL,
    AttentionPolicy.HYBRID: SchedulerProfile.HYBRID,
    AttentionPolicy.PLANNING: SchedulerProfile.HYBRID,
    AttentionPolicy.MONITORING: SchedulerProfile.ANALYTICAL,
    AttentionPolicy.EXECUTION: SchedulerProfile.HYBRID,
}


def scheduler_profile_from_attention(policy: AttentionPolicy) -> SchedulerProfile:
    """Deriva o perfil do scheduler a partir da :class:`~AttentionPolicy` do allocator."""
    return _POLICY_TO_SCHEDULER[policy]


# ── Factores do score ────────────────────────────────────────────────


def _recency_factor(block: ContextBlock, *, now: float) -> float:
    raw = block.metadata.get("created_at")
    if raw is None:
        return float(block.recency_score)
    try:
        age = max(0.0, now - float(raw))
    except (TypeError, ValueError):
        return float(block.recency_score)
    half_life = 3600.0
    return float(0.5 ** (age / half_life))


def _confidence_factor(block: ContextBlock) -> float:
    raw = block.metadata.get("confidence")
    if raw is not None:
        try:
            return max(0.05, min(1.0, float(raw)))
        except (TypeError, ValueError):
            pass
    return max(0.05, min(1.0, float(block.confidence)))


def _coverage_factor(block: ContextBlock) -> float:
    """Extrai cobertura do bloco (metadata ou default 1.0)."""
    raw = block.metadata.get("coverage_scoring")
    if raw is not None:
        try:
            return max(0.1, min(1.0, float(raw)))
        except (TypeError, ValueError):
            pass
    cov = block.metadata.get("coverage")
    if isinstance(cov, dict):
        labels = cov.get("labels", {})
        if isinstance(labels, dict) and "picked" in labels and "pool_rows" in labels:
            pool = max(1, int(labels["pool_rows"]))
            return min(1.0, int(labels["picked"]) / pool)
    return 1.0


def _importance_factor(block: ContextBlock) -> float:
    """Importância via cognitive_weight ou heurística por role."""
    cw = float(block.cognitive_weight)
    if cw != 1.0:
        return max(0.1, min(2.0, cw))
    if block.role == ContextRole.SYSTEM:
        return 1.1
    if block.role == ContextRole.USER:
        return 1.05
    if block.role == ContextRole.DATA:
        return 1.0
    return 0.95


def _density_factor(block: ContextBlock) -> float:
    return max(0.1, min(2.0, float(block.information_density)))


def _profile_multiplier(block: ContextBlock, profile: SchedulerProfile) -> float:
    fk = block.metadata.get("fusion_kind") if isinstance(block.metadata, Mapping) else None

    if profile == SchedulerProfile.ANALYTICAL:
        m = 1.0
        if block.role == ContextRole.DATA:
            m *= 1.22
        if fk in ("evidence", "digest"):
            m *= 1.14
        if block.source == ContextSource.BROKER:
            m *= 1.06
        return m

    if profile == SchedulerProfile.CONVERSATIONAL:
        m = 1.0
        if block.role in (ContextRole.USER, ContextRole.ASSISTANT):
            m *= 1.28
        if block.source == ContextSource.MEMORY or block.role == ContextRole.CONTEXT:
            m *= 1.12
        if block.source == ContextSource.USER_INPUT:
            m *= 1.08
        return m

    m = 1.0
    if fk:
        m *= 1.06
    if block.role in (ContextRole.USER, ContextRole.DATA):
        m *= 1.05
    return m


# ── Score composto ───────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SchedulerScoreBreakdown:
    """Componentes individuais do score para debug/traçabilidade."""

    relevance: float
    recency: float
    confidence: float
    coverage: float
    importance: float
    density: float
    profile_multiplier: float
    composite: float


def composite_score(
    block: ContextBlock,
    profile: SchedulerProfile,
    *,
    now: float | None = None,
) -> float:
    """Score composto: ``relevance × recency × confidence × coverage^0.3 × importance^0.4 × density^0.2 × profile``."""
    return compute_score_breakdown(block, profile, now=now).composite


def compute_score_breakdown(
    block: ContextBlock,
    profile: SchedulerProfile,
    *,
    now: float | None = None,
) -> SchedulerScoreBreakdown:
    """Score composto decomposto para rastreabilidade."""
    t = now if now is not None else time.time()
    rel = max(0.0, min(1.0, float(block.relevance_score)))
    rec = _recency_factor(block, now=t)
    conf = _confidence_factor(block)
    cov = _coverage_factor(block)
    imp = _importance_factor(block)
    dens = _density_factor(block)
    pm = _profile_multiplier(block, profile)
    base = rel * rec * conf * (cov ** 0.3) * (imp ** 0.4) * (dens ** 0.2)
    comp = base * pm
    return SchedulerScoreBreakdown(
        relevance=rel,
        recency=rec,
        confidence=conf,
        coverage=cov,
        importance=imp,
        density=dens,
        profile_multiplier=pm,
        composite=comp,
    )


# ── Slot competition DATA vs MEMORY ──────────────────────────────────


def _source_bucket(block: ContextBlock) -> str:
    if block.source == ContextSource.MEMORY or block.role == ContextRole.CONTEXT:
        return "memory"
    if block.role in (ContextRole.DATA, ContextRole.TOOL) or block.source == ContextSource.BROKER:
        return "data"
    return "other"


def _apply_slot_competition(
    blocks: list[ContextBlock],
    policy: AttentionPolicy,
    scored: list[tuple[float, ContextBlock]],
) -> list[tuple[float, ContextBlock]]:
    """
    Ajusta scores de DATA vs MEMORY conforme os pesos da policy (Fase 4.2).

    Se a policy favorece DATA (``source_weights["data"] > source_weights["memory"]``),
    blocos MEMORY recebem um penalty leve e vice-versa.
    """
    pol_def = policy_definition(policy)
    data_w = float(pol_def.source_weights.get("data", 1.0))
    mem_w = float(pol_def.source_weights.get("memory", 1.0))
    if abs(data_w - mem_w) < 0.01:
        return scored

    data_bias = data_w / max(data_w, mem_w)
    mem_bias = mem_w / max(data_w, mem_w)

    out: list[tuple[float, ContextBlock]] = []
    for score, b in scored:
        bucket = _source_bucket(b)
        if bucket == "data":
            out.append((score * data_bias, b))
        elif bucket == "memory":
            out.append((score * mem_bias, b))
        else:
            out.append((score, b))
    return out


# ── Schedule ─────────────────────────────────────────────────────────


def schedule_blocks(
    blocks: Sequence[ContextBlock],
    profile: SchedulerProfile,
    *,
    now: float | None = None,
    policy: AttentionPolicy | None = None,
) -> list[ContextBlock]:
    """
    Reordena blocos por ``composite_score`` descrescente, com slot competition
    DATA vs MEMORY quando ``policy`` é fornecida.
    """
    t = now if now is not None else time.time()
    ranked: list[tuple[float, ContextBlock]] = [
        (composite_score(b, profile, now=t), b) for b in blocks
    ]

    if policy is not None:
        ranked = _apply_slot_competition(list(blocks), policy, ranked)

    ranked.sort(key=lambda x: (-x[0], x[1].block_id or ""))

    out: list[ContextBlock] = []
    for score, b in ranked:
        new_rel = min(1.0, score)
        md: dict[str, object] = dict(b.metadata)
        md["scheduler_score"] = score
        md["scheduler_profile"] = profile.value
        out.append(dataclasses.replace(b, relevance_score=new_rel, metadata=md))
    return out
