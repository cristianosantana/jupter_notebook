"""Fase 4 — Context Fusion real + Scheduler cognitivo."""

from __future__ import annotations

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.runtime import (
    AttentionPolicy,
    SchedulerProfile,
    SchedulerScoreBreakdown,
    composite_score,
    compute_score_breakdown,
    schedule_blocks,
)
from orion_mcp_v3.runtime.context_fusion import (
    ContextFusion,
    FusionSource,
    classify_fusion_source,
)


# ── 4.1 FusionSource + classify ─────────────────────────────────────


def test_fusion_source_enum_values() -> None:
    assert FusionSource.SYSTEM.value == "system"
    assert FusionSource.DATA.value == "data"
    assert FusionSource.DIGEST.value == "digest"
    assert FusionSource.MEMORY.value == "memory"
    assert FusionSource.USER.value == "user"
    assert FusionSource.ASSISTANT.value == "assistant"


def test_classify_fusion_source_system() -> None:
    b = ContextBlock("sys", ContextRole.SYSTEM, ContextSource.SYSTEM)
    assert classify_fusion_source(b) == FusionSource.SYSTEM


def test_classify_fusion_source_user() -> None:
    b = ContextBlock("hi", ContextRole.USER, ContextSource.USER_INPUT)
    assert classify_fusion_source(b) == FusionSource.USER


def test_classify_fusion_source_memory() -> None:
    b = ContextBlock("m", ContextRole.CONTEXT, ContextSource.MEMORY)
    assert classify_fusion_source(b) == FusionSource.MEMORY


def test_classify_fusion_source_digest() -> None:
    b = ContextBlock("d", ContextRole.DATA, ContextSource.BROKER, metadata={"fusion_kind": "digest"})
    assert classify_fusion_source(b) == FusionSource.DIGEST


def test_classify_fusion_source_data() -> None:
    b = ContextBlock("d", ContextRole.DATA, ContextSource.BROKER)
    assert classify_fusion_source(b) == FusionSource.DATA


def test_classify_fusion_source_assistant() -> None:
    b = ContextBlock("a", ContextRole.ASSISTANT, ContextSource.MEMORY)
    assert classify_fusion_source(b) == FusionSource.ASSISTANT


# ── 4.1 Context Fusion pipeline ─────────────────────────────────────


def test_fusion_tags_fusion_source_metadata() -> None:
    b = ContextBlock("x", ContextRole.USER, ContextSource.USER_INPUT, block_id="u1")
    r = ContextFusion().fuse([("user", [b])])
    assert r.blocks[0].metadata.get("fusion_source") == "user"


def test_fusion_fusion_sources_used_field() -> None:
    u = ContextBlock("u", ContextRole.USER, ContextSource.USER_INPUT, block_id="u1")
    d = ContextBlock("d", ContextRole.DATA, ContextSource.BROKER, block_id="d1")
    r = ContextFusion().fuse([("user", [u]), ("data", [d])])
    assert "user" in r.fusion_sources_used
    assert "data" in r.fusion_sources_used


def test_fusion_normalizes_whitespace() -> None:
    b = ContextBlock("  hello   world  ", ContextRole.USER, ContextSource.USER_INPUT, block_id="u1")
    r = ContextFusion().fuse([("user", [b])])
    assert r.blocks[0].text == "hello world"


def test_fusion_dedupe_keeps_first_layer() -> None:
    shared = "dup-id"
    a = ContextBlock("first", ContextRole.USER, ContextSource.USER_INPUT, block_id=shared, relevance_score=0.1)
    b = ContextBlock("second", ContextRole.CONTEXT, ContextSource.MEMORY, block_id=shared, relevance_score=0.9)
    r = ContextFusion().fuse([("user", [a]), ("memory", [b])])
    assert len(r.blocks) == 1
    assert r.blocks[0].text == "first"
    assert shared in r.dropped_ids


def test_fusion_static_order_by_role_without_policy() -> None:
    sys_b = ContextBlock("s", ContextRole.SYSTEM, ContextSource.SYSTEM, block_id="s1", relevance_score=0.5)
    usr = ContextBlock("u", ContextRole.USER, ContextSource.USER_INPUT, block_id="u1", relevance_score=0.9)
    r = ContextFusion().fuse([("a", [usr, sys_b])])
    assert r.blocks[0].role == ContextRole.SYSTEM
    assert r.blocks[1].role == ContextRole.USER


def test_fusion_dynamic_order_with_policy() -> None:
    data = ContextBlock(
        "dados analíticos", ContextRole.DATA, ContextSource.BROKER,
        block_id="d1", relevance_score=0.8,
    )
    mem = ContextBlock(
        "memória", ContextRole.CONTEXT, ContextSource.MEMORY,
        block_id="m1", relevance_score=0.8,
    )
    r = ContextFusion().fuse(
        [("data", [data]), ("memory", [mem])],
        policy=AttentionPolicy.ANALYTICAL,
    )
    assert r.notes == "context_fusion_v2"
    assert len(r.blocks) == 2


def test_fuse_with_policy_shortcut() -> None:
    b = ContextBlock("x", ContextRole.USER, ContextSource.USER_INPUT, block_id="u1")
    r = ContextFusion().fuse_with_policy([("user", [b])], AttentionPolicy.BALANCED)
    assert r.notes == "context_fusion_v2"
    assert len(r.blocks) == 1


# ── 4.2 Scheduler cognitivo ─────────────────────────────────────────


def test_compute_score_breakdown_fields() -> None:
    b = ContextBlock(
        "test", ContextRole.DATA, ContextSource.BROKER,
        block_id="d1", relevance_score=0.8,
        confidence=0.9, information_density=1.2,
    )
    bd = compute_score_breakdown(b, SchedulerProfile.ANALYTICAL, now=1_700_000_000.0)
    assert isinstance(bd, SchedulerScoreBreakdown)
    assert bd.relevance == 0.8
    assert bd.confidence > 0.0
    assert bd.density > 0.0
    assert bd.composite > 0.0
    assert bd.composite == composite_score(b, SchedulerProfile.ANALYTICAL, now=1_700_000_000.0)


def test_scheduler_uses_coverage_factor() -> None:
    with_cov = ContextBlock(
        "d1", ContextRole.DATA, ContextSource.BROKER,
        block_id="d1", relevance_score=0.8,
        metadata={"coverage_scoring": 0.9},
    )
    without_cov = ContextBlock(
        "d2", ContextRole.DATA, ContextSource.BROKER,
        block_id="d2", relevance_score=0.8,
    )
    bd1 = compute_score_breakdown(with_cov, SchedulerProfile.ANALYTICAL, now=1_700_000_000.0)
    bd2 = compute_score_breakdown(without_cov, SchedulerProfile.ANALYTICAL, now=1_700_000_000.0)
    assert bd1.coverage == 0.9
    assert bd2.coverage == 1.0


def test_scheduler_uses_importance_from_cognitive_weight() -> None:
    heavy = ContextBlock(
        "important", ContextRole.DATA, ContextSource.BROKER,
        block_id="h1", relevance_score=0.7, cognitive_weight=1.5,
    )
    normal = ContextBlock(
        "normal", ContextRole.DATA, ContextSource.BROKER,
        block_id="n1", relevance_score=0.7, cognitive_weight=1.0,
    )
    bd_h = compute_score_breakdown(heavy, SchedulerProfile.ANALYTICAL, now=1_700_000_000.0)
    bd_n = compute_score_breakdown(normal, SchedulerProfile.ANALYTICAL, now=1_700_000_000.0)
    assert bd_h.importance > bd_n.importance
    assert bd_h.composite > bd_n.composite


def test_scheduler_uses_information_density() -> None:
    dense = ContextBlock(
        "dense", ContextRole.DATA, ContextSource.BROKER,
        block_id="d1", relevance_score=0.7, information_density=1.5,
    )
    sparse = ContextBlock(
        "sparse", ContextRole.DATA, ContextSource.BROKER,
        block_id="s1", relevance_score=0.7, information_density=0.5,
    )
    bd_d = compute_score_breakdown(dense, SchedulerProfile.ANALYTICAL, now=1_700_000_000.0)
    bd_s = compute_score_breakdown(sparse, SchedulerProfile.ANALYTICAL, now=1_700_000_000.0)
    assert bd_d.density > bd_s.density
    assert bd_d.composite > bd_s.composite


def test_slot_competition_analytical_favors_data() -> None:
    data = ContextBlock(
        "d", ContextRole.DATA, ContextSource.BROKER,
        block_id="d1", relevance_score=0.5,
    )
    mem = ContextBlock(
        "m", ContextRole.CONTEXT, ContextSource.MEMORY,
        block_id="m1", relevance_score=0.5,
    )
    out = schedule_blocks(
        [mem, data], SchedulerProfile.ANALYTICAL,
        now=1_700_000_000.0, policy=AttentionPolicy.ANALYTICAL,
    )
    assert out[0].block_id == "d1"


def test_slot_competition_memory_focused_favors_memory() -> None:
    data = ContextBlock(
        "d", ContextRole.DATA, ContextSource.BROKER,
        block_id="d1", relevance_score=0.5,
    )
    mem = ContextBlock(
        "m", ContextRole.CONTEXT, ContextSource.MEMORY,
        block_id="m1", relevance_score=0.5,
    )
    out = schedule_blocks(
        [data, mem], SchedulerProfile.CONVERSATIONAL,
        now=1_700_000_000.0, policy=AttentionPolicy.MEMORY_FOCUSED,
    )
    assert out[0].block_id == "m1"


def test_schedule_blocks_tags_metadata() -> None:
    b = ContextBlock("x", ContextRole.USER, ContextSource.USER_INPUT, block_id="u1", relevance_score=0.5)
    out = schedule_blocks([b], SchedulerProfile.CONVERSATIONAL, now=1_700_000_000.0)
    assert "scheduler_score" in out[0].metadata
    assert "scheduler_profile" in out[0].metadata
    assert out[0].metadata["scheduler_profile"] == "conversational"
