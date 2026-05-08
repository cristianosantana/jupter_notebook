"""Bloco 6 ORDEM_IMPLEMENTAÇÃO — EvidenceBuilder → EvidenceBlock."""

from __future__ import annotations

from orion_mcp_v3.broker import EvidenceBuilder, evidence_block_to_digest
from orion_mcp_v3.contracts import EvidenceBlock


def test_evidence_block_baseline_variation_anomalies() -> None:
    rows = [{"id": i, "v": float(x)} for i, x in enumerate([10.0, 10.0, 10.0, 100.0], start=1)]
    block = EvidenceBuilder(z_threshold=1.5).build(rows, value_key="v")
    assert isinstance(block, EvidenceBlock)
    assert block.insights["baseline"]["count"] == 4
    assert block.insights["variation"]["stdev"] > 0
    assert block.insights["anomalies"]["count"] >= 1
    assert block.confidence > 0.35
    assert len(block.provenance) == 1


def test_evidence_temporal_trend_up() -> None:
    rows = [
        {"created_at": "2024-01-15", "amt": 100.0},
        {"created_at": "2024-02-10", "amt": 200.0},
    ]
    block = EvidenceBuilder().build(rows, value_key="amt", time_key="created_at")
    tr = block.insights["trends"]
    assert tr["status"] == "ok"
    assert tr["direction"] == "up"
    assert tr.get("period_over_period_change") == 1.0


def test_evidence_no_numeric_values() -> None:
    block = EvidenceBuilder().build([{"id": 1}], value_key="missing")
    assert block.insights["baseline"]["status"] == "no_numeric_values"
    assert "Sem valores numéricos" in block.summary


def test_evidence_block_to_digest_bridge() -> None:
    rows = [{"x": 1.0}, {"x": 3.0}]
    block = EvidenceBuilder().build(rows, value_key="x")
    digest = evidence_block_to_digest(block)
    assert digest.summary == block.summary
    assert digest.confidence == block.confidence
    assert digest.volume == 2
