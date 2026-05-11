from __future__ import annotations

"""
Scheduler score-based (§11 ORDEM_IMPLEMENTAÇÃO): ordenação por pontuação composta antes do allocator.

Score base (ROADMAP_EXECUTÁVEL): ``relevance × recency × confidence``, com multiplicadores por
:class:`SchedulerProfile` (analytical / conversational / hybrid).
"""

import dataclasses
import time
from collections.abc import Mapping, Sequence
from enum import Enum

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy


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


def _recency_factor(block: ContextBlock, *, now: float) -> float:
    raw = block.metadata.get("created_at")
    if raw is None:
        return 1.0
    try:
        age = max(0.0, now - float(raw))
    except (TypeError, ValueError):
        return 1.0
    half_life = 3600.0
    return float(0.5 ** (age / half_life))


def _confidence_factor(block: ContextBlock) -> float:
    raw = block.metadata.get("confidence")
    if raw is not None:
        try:
            return max(0.05, min(1.0, float(raw)))
        except (TypeError, ValueError):
            pass
    return max(0.05, min(1.0, float(block.relevance_score)))


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


def composite_score(
    block: ContextBlock,
    profile: SchedulerProfile,
    *,
    now: float | None = None,
) -> float:
    """Combina relevância, recência, confiança e multiplicador de perfil."""
    t = now if now is not None else time.time()
    rel = max(0.0, min(1.0, float(block.relevance_score)))
    rec = _recency_factor(block, now=t)
    conf = _confidence_factor(block)
    base = rel * rec * conf
    return base * _profile_multiplier(block, profile)


def schedule_blocks(
    blocks: Sequence[ContextBlock],
    profile: SchedulerProfile,
    *,
    now: float | None = None,
) -> list[ContextBlock]:
    """
    Reordena blocos por ``composite_score`` descrescente e grava score em metadados
    (``scheduler_score``, ``scheduler_profile``), actualizando ``relevance_score`` para o allocator.
    """
    t = now if now is not None else time.time()
    ranked: list[tuple[float, ContextBlock]] = [
        (composite_score(b, profile, now=t), b) for b in blocks
    ]
    ranked.sort(key=lambda x: (-x[0], x[1].block_id or ""))

    out: list[ContextBlock] = []
    for score, b in ranked:
        new_rel = min(1.0, score)
        md: dict[str, object] = dict(b.metadata)
        md["scheduler_score"] = score
        md["scheduler_profile"] = profile.value
        out.append(dataclasses.replace(b, relevance_score=new_rel, metadata=md))
    return out
