"""
§14 ORDEM_IMPLEMENTAÇÃO — DOCUMENTAÇÃO E TESTES (bateria consolidada).

Cobre explicitamente: drift, proveniência, alocação de atenção, orquestração e fusão.
Os módulos subjacentes têm também testes unitários dispersos; este ficheiro serve de
checklist de regressão para a fase final do guia.
"""

from __future__ import annotations

from orion_mcp_v3.contracts.context_block import ContextBlock, ContextRole, ContextSource
from orion_mcp_v3.contracts.digest import AnalyticalDigest
from orion_mcp_v3.runtime import (
    AttentionPolicy,
    CognitiveOrchestrator,
    allocate,
    elastic_free_tier_params,
    estimate_tokens,
    policy_shares,
)
from orion_mcp_v3.runtime.context_fusion import ContextFusion
from orion_mcp_v3.runtime.drift_guard import DriftGuard
from orion_mcp_v3.runtime.provenance import (
    CoverageInfo,
    ProvenanceAnchor,
    merge_coverage_infos,
    merge_provenance_anchors,
)


class TestDecimoQuartoDrift:
    """DriftGuard — digest anterior vs actual."""

    def test_no_previous_never_recommends_refresh(self) -> None:
        cur = AnalyticalDigest("x", volume=10, confidence=0.5)
        r = DriftGuard().evaluate(None, cur)
        assert r.refresh_recommended is False
        assert r.signals == ()

    def test_confidence_drop_emits_signal(self) -> None:
        prev = AnalyticalDigest("old", volume=5, confidence=0.95)
        cur = AnalyticalDigest("new", volume=5, confidence=0.5)
        r = DriftGuard(confidence_drop_threshold=0.12, volume_change_ratio=99.0).evaluate(prev, cur)
        assert any(s.code == "confidence_drop" for s in r.signals)
        assert r.refresh_recommended is True

    def test_volume_ratio_emits_signal(self) -> None:
        prev = AnalyticalDigest("a", volume=2, confidence=0.9)
        cur = AnalyticalDigest("b", volume=10, confidence=0.9)
        r = DriftGuard(confidence_drop_threshold=0.99, volume_change_ratio=4.0).evaluate(prev, cur)
        assert any(s.code == "volume_shift" for s in r.signals)


class TestDecimoQuartoProvenance:
    """Coverage + âncoras — merge determinístico."""

    def test_merge_coverage_infos_prefixes_layers(self) -> None:
        a = CoverageInfo(labels={"k": 1}, notes="a")
        b = CoverageInfo(labels={"k": 2}, notes="b")
        m = merge_coverage_infos(a, b, notes="merged")
        assert m.labels["layer_0_k"] == 1
        assert m.labels["layer_1_k"] == 2
        assert m.notes == "merged"

    def test_merge_provenance_anchors_dedupes(self) -> None:
        p1 = ProvenanceAnchor("id1", "src", ("a",))
        p2 = ProvenanceAnchor("id1", "src", ("b",))
        p3 = ProvenanceAnchor("id2", "src", ())
        out = merge_provenance_anchors((p1, p2), (p3,))
        assert len(out) == 2
        assert out[0].artifact_id == "id1"


class TestDecimoQuartoAttentionAllocation:
    """Política de atenção + allocator (incl. caminho elástico DATA vs MEMORY)."""

    def test_policy_shares_sum_to_one(self) -> None:
        for pol in AttentionPolicy:
            s = policy_shares(pol)
            total = s.system + s.essence + s.free
            assert abs(total - 1.0) < 0.02

    def test_elastic_params_are_bounded(self) -> None:
        for pol in AttentionPolicy:
            e = elastic_free_tier_params(pol)
            assert 0.0 <= e.dialogue_fraction_of_free <= 1.0
            assert 0.0 <= e.data_share_of_remainder <= 1.0
            assert 0.0 <= e.elasticity <= 1.0

    def test_allocate_respects_token_budget(self) -> None:
        data = ContextBlock("d" * 400, ContextRole.DATA, ContextSource.BROKER, relevance_score=0.5)
        mem = ContextBlock("m" * 400, ContextRole.CONTEXT, ContextSource.MEMORY, relevance_score=0.5)
        out = allocate([data, mem], max_tokens=50, policy=AttentionPolicy.ANALYTICAL).fitted_blocks
        assert sum(estimate_tokens(b.text) for b in out) <= 50


class TestDecimoQuartoOrchestration:
    """CognitiveOrchestrator — tail do pipeline até prompt."""

    def test_finalize_prompt_chain(self) -> None:
        r = CognitiveOrchestrator().finalize_prompt(
            "olá",
            policy=AttentionPolicy.CONVERSATIONAL,
            memory_blocks=(),
            max_tokens=256,
        )
        assert r.fusion.layer_priority[0] == "user"
        assert "[USER]" in r.prompt_text
        assert len(r.packed_blocks) >= 1


class TestDecimoQuartoFusion:
    """ContextFusion — prioridade de camada + dedupe."""

    def test_layer_order_wins(self) -> None:
        bid = "dup"
        low = ContextBlock("a", ContextRole.DATA, ContextSource.BROKER, block_id=bid, relevance_score=0.99)
        high_layer = ContextBlock("b", ContextRole.DATA, ContextSource.MEMORY, block_id=bid, relevance_score=0.1)
        res = ContextFusion().fuse((("memory", (high_layer,)), ("broker", (low,))))
        assert len(res.blocks) == 1
        assert res.blocks[0].text == "b"
        assert bid in res.dropped_ids
