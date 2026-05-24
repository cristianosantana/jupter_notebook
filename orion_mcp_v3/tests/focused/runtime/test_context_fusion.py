"""ContextFusion (§9): dedupe, prioridade de camada e ordenação por papel."""

from __future__ import annotations

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.runtime.context_fusion import ContextFusion


def test_fusion_first_layer_wins_on_same_block_id() -> None:
    shared_id = "shared-key"
    user_first = ContextBlock(
        "user says A",
        ContextRole.USER,
        ContextSource.USER_INPUT,
        block_id=shared_id,
        relevance_score=0.1,
    )
    memory_dup = ContextBlock(
        "memory says B",
        ContextRole.CONTEXT,
        ContextSource.MEMORY,
        block_id=shared_id,
        relevance_score=0.99,
    )
    r = ContextFusion().fuse((("user", (user_first,)), ("memory", (memory_dup,))))
    assert len(r.blocks) == 1
    assert r.blocks[0].text == "user says A"
    assert r.blocks[0].metadata.get("fusion_layer") == "user"
    assert shared_id in r.dropped_ids


def test_fusion_sorts_by_role_then_relevance() -> None:
    sys_b = ContextBlock("s", ContextRole.SYSTEM, ContextSource.SYSTEM, block_id="sys-1", relevance_score=0.5)
    usr_hi = ContextBlock("u", ContextRole.USER, ContextSource.USER_INPUT, block_id="u1", relevance_score=0.9)
    usr_lo = ContextBlock("u2", ContextRole.USER, ContextSource.USER_INPUT, block_id="u2", relevance_score=0.1)
    r = ContextFusion().fuse((("a", (usr_lo, sys_b, usr_hi)),))
    assert [b.text for b in r.blocks] == ["s", "u", "u2"]
