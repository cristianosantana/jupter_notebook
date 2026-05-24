"""CognitiveOrchestrator §12 — fusão + scheduler + allocator + prompt."""

from __future__ import annotations

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.runtime import AttentionPolicy, CognitiveOrchestrator


def test_finalize_prompt_produces_non_empty_prompt() -> None:
    utterance = "quantos registos?"
    user_like = ContextBlock(
        utterance,
        ContextRole.USER,
        ContextSource.USER_INPUT,
        block_id="u",
        relevance_score=1.0,
    )
    orch = CognitiveOrchestrator()
    r = orch.finalize_prompt(
        utterance,
        policy=AttentionPolicy.ANALYTICAL,
        memory_blocks=[user_like],
        max_tokens=512,
    )
    assert "[USER]" in r.prompt_text
    assert len(r.packed_blocks) >= 1
    assert r.fusion.layer_priority == ("system", "user", "memory")
