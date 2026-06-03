"""CognitiveOrchestrator §12 — fusão + scheduler + allocator + prompt."""

from __future__ import annotations

from orion_mcp_v3.broker.evidence_builder import EvidenceBuilder
from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.contracts.evidence_contract import EvidenceContract
from orion_mcp_v3.contracts.reasoning_result import AnalyticalReasoningResult, AnswerMode
from orion_mcp_v3.runtime import AttentionPolicy, CognitiveOrchestrator
from orion_mcp_v3.runtime.cognitive_orchestrator import build_fusion_layers


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


def test_fusion_layers_place_evidence_before_memory_context() -> None:
    evidence = EvidenceBuilder().build(
        [{"total_faturamento": 100.0}],
        value_key="total_faturamento",
    )
    essence = ContextBlock(
        "memória destilada",
        ContextRole.CONTEXT,
        ContextSource.MEMORY,
        block_id="essence",
    )
    memory = ContextBlock(
        "memória episódica",
        ContextRole.CONTEXT,
        ContextSource.MEMORY,
        block_id="memory",
    )

    layers = build_fusion_layers(
        "qual o faturamento?",
        evidence=evidence,
        essence_blocks=[essence],
        memory_blocks=[memory],
    )

    assert tuple(name for name, _ in layers) == ("user", "evidence", "essence", "memory")


def test_fusion_layers_place_reasoning_after_evidence_before_memory() -> None:
    evidence = EvidenceBuilder().build(
        [{"total_faturamento": 100.0}],
        value_key="total_faturamento",
    )
    reasoning = AnalyticalReasoningResult(
        facts=("Evidência analítica disponível.",),
        evidence_contract=EvidenceContract.present(row_count=1),
        answer_mode=AnswerMode.EXECUTIVE,
    )
    memory = ContextBlock(
        "memória episódica",
        ContextRole.CONTEXT,
        ContextSource.MEMORY,
        block_id="memory",
    )

    layers = build_fusion_layers(
        "resumo executivo",
        evidence=evidence,
        reasoning_result=reasoning,
        memory_blocks=[memory],
    )

    assert tuple(name for name, _ in layers) == ("user", "evidence", "reasoning", "memory")
    reasoning_block = layers[2][1][0]
    assert reasoning_block.metadata["fusion_kind"] == "reasoning_result"
    assert reasoning_block.metadata["answer_mode"] == "executive"
