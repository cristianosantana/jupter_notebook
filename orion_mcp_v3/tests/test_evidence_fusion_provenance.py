"""Evidence + provenance preservados na fusão cognitiva."""

from __future__ import annotations

from orion_mcp_v3.broker.evidence_builder import EvidenceBuilder
from orion_mcp_v3.contracts.context_block import ContextSource
from orion_mcp_v3.contracts.provenance import CoverageInfo
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy
from orion_mcp_v3.runtime.cognitive_orchestrator import CognitiveOrchestrator, build_fusion_layers
from orion_mcp_v3.runtime.context_fusion import ContextFusion, classify_fusion_source, FusionSource


def test_evidence_builder_sets_coverage_and_provenance() -> None:
    rows = [
        {"mes": "2026-01", "total_faturamento": 1000.0},
        {"mes": "2026-02", "total_faturamento": 1200.0},
        {"mes": "2026-03", "total_faturamento": 900.0},
    ]
    eb = EvidenceBuilder().build(
        rows,
        value_key="total_faturamento",
        time_key="mes",
    )
    assert eb.confidence > 0
    assert isinstance(eb.coverage, CoverageInfo)
    assert len(eb.coverage.labels) >= 1
    assert len(eb.provenance) >= 1


def test_fusion_prioritizes_evidence_data_over_memory() -> None:
    rows = [{"total_faturamento": 500.0}]
    eb = EvidenceBuilder().build(rows, value_key="total_faturamento")
    layers = build_fusion_layers("pergunta", evidence=eb)
    fusion = ContextFusion().fuse(layers, policy=AttentionPolicy.ANALYTICAL)
    data_blocks = [b for b in fusion.blocks if classify_fusion_source(b) == FusionSource.DATA]
    memory_blocks = [b for b in fusion.blocks if classify_fusion_source(b) == FusionSource.MEMORY]
    assert data_blocks
    if memory_blocks:
        assert data_blocks[0].relevance_score >= memory_blocks[0].relevance_score


def test_orchestrator_propagates_provenance_in_evidence_block_metadata() -> None:
    rows = [{"total_faturamento": 100.0}, {"total_faturamento": 200.0}]
    eb = EvidenceBuilder().build(rows, value_key="total_faturamento")
    orch = CognitiveOrchestrator()
    result = orch.finalize_prompt(
        "qual o total?",
        policy=AttentionPolicy.ANALYTICAL,
        evidence=eb,
        max_tokens=2048,
    )
    evidence_cbs = [
        b
        for b in result.packed_blocks
        if b.source == ContextSource.BROKER and b.metadata.get("fusion_kind") == "evidence"
    ]
    assert evidence_cbs
    md = evidence_cbs[0].metadata
    assert md.get("provenance_count", 0) >= 1 or "coverage_labels" in md
