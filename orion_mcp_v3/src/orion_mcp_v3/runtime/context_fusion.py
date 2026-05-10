"""
ContextFusion — deduplicação, prioridade por camada, ordenação e resolução de conflitos (§9).

Junta blocos provenientes de analytics, memória, evidência, etc., com ordem de camada explícita:
a primeira camada na sequência ``layers`` ganha em caso de chave de deduplicação igual.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, replace

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole


def _dedupe_key(b: ContextBlock) -> str:
    if b.block_id:
        return f"id:{b.block_id}"
    return f"{b.role.name}:{b.source.name}:{hash(b.text) & 0xFFFF_FFFF}"


_ROLE_ORDER: dict[ContextRole, int] = {
    ContextRole.SYSTEM: 0,
    ContextRole.USER: 1,
    ContextRole.ASSISTANT: 2,
    ContextRole.TOOL: 3,
    ContextRole.DATA: 4,
    ContextRole.CONTEXT: 5,
    ContextRole.NEUTRAL: 6,
}


@dataclass(frozen=True, slots=True)
class ContextFusionResult:
    """Blocos fundidos + ids descartados por conflito / deduplicação."""

    blocks: tuple[ContextBlock, ...]
    dropped_ids: tuple[str, ...]
    notes: str | None
    layer_priority: tuple[str, ...]


class ContextFusion:
    """
    * **deduplicação**: mesma chave que em :func:`resolve_duplicate_blocks`;
    * **conflito**: vence o bloco da camada com menor índice em ``layers``; empate por maior ``relevance_score``;
    * **ordenação**: papel semântico (SYSTEM→…→NEUTRAL), depois ``relevance_score`` decrescente.
    """

    def fuse(self, layers: Sequence[tuple[str, Sequence[ContextBlock]]]) -> ContextFusionResult:
        layer_names: list[str] = []
        grouped: dict[str, list[tuple[ContextBlock, int, str]]] = defaultdict(list)

        for rank, (name, seq) in enumerate(layers):
            layer_names.append(name)
            for b in seq:
                grouped[_dedupe_key(b)].append((b, rank, name))

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

        winners.sort(
            key=lambda b: (_ROLE_ORDER.get(b.role, 99), -b.relevance_score),
        )

        return ContextFusionResult(
            blocks=tuple(winners),
            dropped_ids=tuple(dropped_ids),
            notes="context_fusion_layer_priority_v1",
            layer_priority=tuple(layer_names),
        )
