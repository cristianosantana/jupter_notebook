"""
ContextFusion real (Fase 4.1) — pipeline ``normalize → dedupe → rank → allocate → render``
com ordenação dinâmica por :class:`~AttentionPolicy`.

Sources canónicas: SYSTEM, DATA, DIGEST, MEMORY, USER, ASSISTANT.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace
from enum import Enum

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.runtime.attention_policy import (
    AttentionPolicy,
    AttentionPolicyDefinition,
    policy_definition,
)


class FusionSource(Enum):
    """Tipos canónicos de fonte no pipeline de fusão."""

    SYSTEM = "system"
    DATA = "data"
    DIGEST = "digest"
    MEMORY = "memory"
    USER = "user"
    ASSISTANT = "assistant"


def classify_fusion_source(block: ContextBlock) -> FusionSource:
    """Infere a :class:`FusionSource` canónica a partir de role/source/metadata."""
    fk = block.metadata.get("fusion_kind") if isinstance(block.metadata, dict) else None
    if fk == "digest":
        return FusionSource.DIGEST
    if block.role == ContextRole.SYSTEM or block.source == ContextSource.SYSTEM:
        return FusionSource.SYSTEM
    if block.role == ContextRole.USER or block.source == ContextSource.USER_INPUT:
        return FusionSource.USER
    if block.role == ContextRole.ASSISTANT:
        return FusionSource.ASSISTANT
    if block.source == ContextSource.MEMORY or block.role == ContextRole.CONTEXT:
        return FusionSource.MEMORY
    if block.role in (ContextRole.DATA, ContextRole.TOOL) or block.source == ContextSource.BROKER:
        return FusionSource.DATA
    return FusionSource.DATA


# ── Normalização ─────────────────────────────────────────────────────

def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip())


def _normalize_block(block: ContextBlock) -> ContextBlock:
    """Normaliza whitespace e garante metadata ``fusion_source``."""
    norm = _normalize_text(block.text)
    fs = classify_fusion_source(block)
    md = {**dict(block.metadata), "fusion_source": fs.value}
    if norm != block.text:
        return replace(block, text=norm, metadata=md)
    return replace(block, metadata=md)


# ── Deduplicação ─────────────────────────────────────────────────────

def _dedupe_key(b: ContextBlock) -> str:
    if b.block_id:
        return f"id:{b.block_id}"
    return f"{b.role.name}:{b.source.name}:{hash(b.text) & 0xFFFF_FFFF}"


# ── Ranking dinâmico por policy ──────────────────────────────────────

_FUSION_SOURCE_TO_BUCKET: dict[FusionSource, str] = {
    FusionSource.SYSTEM: "system",
    FusionSource.DATA: "data",
    FusionSource.DIGEST: "data",
    FusionSource.MEMORY: "memory",
    FusionSource.USER: "user_dialogue",
    FusionSource.ASSISTANT: "user_dialogue",
}


def _dynamic_rank_score(block: ContextBlock, policy_def: AttentionPolicyDefinition) -> float:
    """Score de ranking: ``compute_attention_score × source_weight`` da policy."""
    fs = classify_fusion_source(block)
    bucket = _FUSION_SOURCE_TO_BUCKET.get(fs, "other")
    weight = float(policy_def.source_weights.get(bucket, 1.0))
    return block.compute_attention_score() * weight


# ── Resultado ────────────────────────────────────────────────────────

@dataclass(frozen=True, slots=True)
class ContextFusionResult:
    """Blocos fundidos + ids descartados por conflito / deduplicação."""

    blocks: tuple[ContextBlock, ...]
    dropped_ids: tuple[str, ...]
    notes: str | None
    layer_priority: tuple[str, ...]
    fusion_sources_used: tuple[str, ...]


_ROLE_ORDER: dict[ContextRole, int] = {
    ContextRole.SYSTEM: 0,
    ContextRole.USER: 1,
    ContextRole.ASSISTANT: 2,
    ContextRole.TOOL: 3,
    ContextRole.DATA: 4,
    ContextRole.CONTEXT: 5,
    ContextRole.NEUTRAL: 6,
}


class ContextFusion:
    """
    Pipeline: normalize → dedupe → rank (dinâmico por policy) → output.

    ``fuse()`` mantém compatibilidade retroactiva (layers como tuplos ``(name, blocks)``).
    ``fuse_with_policy()`` aceita ``AttentionPolicy`` para ordenação dinâmica.
    """

    def fuse(
        self,
        layers: Sequence[tuple[str, Sequence[ContextBlock]]],
        *,
        policy: AttentionPolicy | None = None,
    ) -> ContextFusionResult:
        layer_names: list[str] = []
        grouped: dict[str, list[tuple[ContextBlock, int, str]]] = defaultdict(list)

        for rank, (name, seq) in enumerate(layers):
            layer_names.append(name)
            for b in seq:
                nb = _normalize_block(b)
                grouped[_dedupe_key(nb)].append((nb, rank, name))

        winners: list[ContextBlock] = []
        dropped_ids: list[str] = []

        for _key, items in grouped.items():
            best_b, best_rank, best_layer = min(
                items,
                key=lambda it: (it[1], -it[0].relevance_score),
            )
            md = dict(best_b.metadata)
            md["fusion_layer"] = best_layer
            md["fusion_priority_rank"] = best_rank
            winners.append(replace(best_b, metadata=md))

            for b, _r, _ln in items:
                if b is not best_b and b.block_id:
                    dropped_ids.append(b.block_id)

        # Rank: dinâmico por policy ou estático por role
        if policy is not None:
            pol_def = policy_definition(policy)
            winners.sort(
                key=lambda b: (-_dynamic_rank_score(b, pol_def), _ROLE_ORDER.get(b.role, 99), b.block_id or ""),
            )
        else:
            winners.sort(
                key=lambda b: (_ROLE_ORDER.get(b.role, 99), -b.relevance_score),
            )

        sources_used = sorted({classify_fusion_source(b).value for b in winners})

        return ContextFusionResult(
            blocks=tuple(winners),
            dropped_ids=tuple(dropped_ids),
            notes="context_fusion_v2" if policy else "context_fusion_layer_priority_v1",
            layer_priority=tuple(layer_names),
            fusion_sources_used=tuple(sources_used),
        )

    def fuse_with_policy(
        self,
        layers: Sequence[tuple[str, Sequence[ContextBlock]]],
        policy: AttentionPolicy,
    ) -> ContextFusionResult:
        """Atalho explícito para fusão com ordenação dinâmica por policy."""
        return self.fuse(layers, policy=policy)
