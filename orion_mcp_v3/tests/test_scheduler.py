"""Scheduler §11 — score composto e perfis analytical / conversational / hybrid."""

from __future__ import annotations

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.runtime import (
    AttentionPolicy,
    SchedulerProfile,
    schedule_blocks,
    scheduler_profile_from_attention,
)


def test_scheduler_profile_from_attention_maps_policies() -> None:
    assert scheduler_profile_from_attention(AttentionPolicy.ANALYTICAL) == SchedulerProfile.ANALYTICAL
    assert scheduler_profile_from_attention(AttentionPolicy.CONVERSATIONAL) == SchedulerProfile.CONVERSATIONAL
    assert scheduler_profile_from_attention(AttentionPolicy.HYBRID) == SchedulerProfile.HYBRID
    assert scheduler_profile_from_attention(AttentionPolicy.PLANNING) == SchedulerProfile.HYBRID


def test_analytical_prefers_evidence_data_blocks() -> None:
    evidence = ContextBlock(
        "ev",
        ContextRole.DATA,
        ContextSource.BROKER,
        block_id="ev1",
        metadata={"fusion_kind": "evidence"},
        relevance_score=0.5,
    )
    filler = ContextBlock(
        "x",
        ContextRole.NEUTRAL,
        ContextSource.OTHER,
        block_id="n1",
        relevance_score=0.55,
    )
    out = schedule_blocks([filler, evidence], SchedulerProfile.ANALYTICAL, now=1_700_000_000.0)
    assert out[0].block_id == "ev1"


def test_conversational_prefers_user_turn() -> None:
    user = ContextBlock(
        "pergunta",
        ContextRole.USER,
        ContextSource.USER_INPUT,
        block_id="u1",
        relevance_score=0.42,
    )
    data = ContextBlock(
        "dados",
        ContextRole.DATA,
        ContextSource.BROKER,
        block_id="d1",
        relevance_score=0.35,
    )
    out = schedule_blocks([data, user], SchedulerProfile.CONVERSATIONAL, now=1_700_000_000.0)
    assert out[0].block_id == "u1"
