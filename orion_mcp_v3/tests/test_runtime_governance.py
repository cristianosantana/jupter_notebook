"""Governança mínima: conflitos + decaimento (guia ORDEM_IMPLEMENTAÇÃO bloco 3)."""

from __future__ import annotations

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.runtime.conflict_resolution import (
    cap_system_blocks,
    resolve_duplicate_blocks,
)
from orion_mcp_v3.runtime.decay import (
    apply_decay,
    apply_decay_to_sequence,
    apply_decay_with_clock,
    resolve_age_seconds,
)


def test_resolve_duplicate_blocks_keeps_highest_score_per_key() -> None:
    # Sem block_id a chave é role+source+hash(texto); duas cópias colapsam no maior score.
    a = ContextBlock("same", ContextRole.USER, ContextSource.USER_INPUT, relevance_score=0.3)
    b = ContextBlock("same", ContextRole.USER, ContextSource.USER_INPUT, relevance_score=0.9)
    r = resolve_duplicate_blocks((a, b))
    assert len(r.blocks) == 1
    assert r.blocks[0] is b
    assert r.dropped_ids == ()

    # Com IDs distintos, são chaves diferentes — ambos permanecem.
    x = ContextBlock(
        "same",
        ContextRole.USER,
        ContextSource.USER_INPUT,
        block_id="x",
        relevance_score=0.3,
    )
    y = ContextBlock(
        "same",
        ContextRole.USER,
        ContextSource.USER_INPUT,
        block_id="y",
        relevance_score=0.9,
    )
    r2 = resolve_duplicate_blocks((x, y))
    assert len(r2.blocks) == 2


def test_cap_system_blocks_keeps_top_scores() -> None:
    blocks = (
        ContextBlock("u", ContextRole.USER, ContextSource.USER_INPUT, relevance_score=1.0),
        ContextBlock("s1", ContextRole.SYSTEM, ContextSource.SYSTEM, block_id="s1", relevance_score=0.2),
        ContextBlock("s2", ContextRole.SYSTEM, ContextSource.SYSTEM, block_id="s2", relevance_score=0.9),
        ContextBlock("s3", ContextRole.SYSTEM, ContextSource.SYSTEM, block_id="s3", relevance_score=0.5),
    )
    r = cap_system_blocks(blocks, max_blocks=2)
    texts = {b.text for b in r.blocks}
    assert "u" in texts
    assert "s2" in texts and "s3" in texts
    assert "s1" not in texts
    assert "s1" in r.dropped_ids


def test_apply_decay_half_life() -> None:
    b = ContextBlock("x", ContextRole.DATA, ContextSource.BROKER, relevance_score=1.0)
    # Uma meia-vida => metade
    out = apply_decay(b, age_seconds=3600.0, half_life_seconds=3600.0, redundancy_penalty=0.0)
    assert abs(out.relevance_score - 0.5) < 1e-9


def test_apply_decay_redundancy_and_min() -> None:
    b = ContextBlock("x", ContextRole.DATA, ContextSource.BROKER, relevance_score=0.8)
    out = apply_decay(b, age_seconds=0.0, half_life_seconds=None, redundancy_penalty=0.9, min_score=0.1)
    assert out.relevance_score == 0.1


def test_resolve_age_and_apply_decay_with_clock() -> None:
    b = ContextBlock(
        "m",
        ContextRole.CONTEXT,
        ContextSource.MEMORY,
        metadata={"created_at": 1000.0},
        relevance_score=1.0,
    )

    assert resolve_age_seconds(b, now=1010.0) == 10.0
    out = apply_decay_with_clock(b, now=1010.0, half_life_seconds=10.0, redundancy_penalty=0.0)
    # 10s age, HL 10s => factor 0.5
    assert abs(out.relevance_score - 0.5) < 1e-9


def test_apply_decay_to_sequence() -> None:
    b0 = ContextBlock("a", ContextRole.USER, ContextSource.USER_INPUT, relevance_score=1.0)
    b1 = ContextBlock("b", ContextRole.USER, ContextSource.USER_INPUT, relevance_score=1.0)
    seq = apply_decay_to_sequence(
        (b0, b1),
        ages_seconds=(3600.0, 0.0),
        half_life_seconds=3600.0,
    )
    assert abs(seq[0].relevance_score - 0.5) < 1e-9
    assert seq[1].relevance_score == 1.0
