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


def test_ranking_in_evidence_summary() -> None:
    """Ranking categórico + partilhas aparecem no sumário e em insights."""
    rows = [
        {"forma_pagamento": "Cartao de Credito", "total_recebido": 65.0},
        {"forma_pagamento": "Pix", "total_recebido": 20.0},
        {"forma_pagamento": "Boleto", "total_recebido": 15.0},
        {"forma_pagamento": "A", "total_recebido": 1.0},
        {"forma_pagamento": "B", "total_recebido": 1.0},
        {"forma_pagamento": "C", "total_recebido": 1.0},
        {"forma_pagamento": "D", "total_recebido": 1.0},
        {"forma_pagamento": "E", "total_recebido": 1.0},
        {"forma_pagamento": "F", "total_recebido": 1.0},
    ]
    block = EvidenceBuilder().build(
        rows,
        value_key="total_recebido",
        label_key="forma_pagamento",
        ranking_top_n=3,
    )
    assert "ranking" in block.insights
    assert len(block.insights["ranking"]) == 3
    assert "65" in block.summary or "Cartao" in block.summary
    assert "ranking_omitted_count" in block.insights
    assert block.insights["ranking_omitted_count"] == 6


def test_dominant_majority() -> None:
    rows = [
        {"cat": "A", "v": 60.0},
        {"cat": "B", "v": 40.0},
    ]
    block = EvidenceBuilder().build(rows, value_key="v", label_key="cat")
    dom = block.insights.get("dominant")
    assert dom is not None
    assert dom["label"] == "A"
    assert dom["is_majority"] is True


def test_concentration_hhi() -> None:
    uniform = [{"k": f"c{i}", "v": 1.0} for i in range(9)]
    b_u = EvidenceBuilder().build(uniform, value_key="v", label_key="k")
    assert b_u.insights["concentration"]["interpretation"] == "baixa"

    dominant = [{"k": "big", "v": 97.0}, {"k": "small", "v": 1.0}, {"k": "tiny", "v": 2.0}]
    b_d = EvidenceBuilder().build(dominant, value_key="v", label_key="k")
    assert b_d.insights["concentration"]["interpretation"] == "alta"


def test_period_coverage() -> None:
    rows = [
        {"data_recebimento": "2026-01-03", "valor": 1.0},
        {"data_recebimento": "2026-04-29", "valor": 2.0},
    ]
    block = EvidenceBuilder().build(rows, value_key="valor", time_key="data_recebimento", grain="day")
    cov = block.insights.get("period_coverage")
    assert cov is not None
    assert cov["date_min"] == "2026-01-03"
    assert cov["date_max"] == "2026-04-29"
    assert cov["days_span"] == 117
    assert "2026-01-03" in block.summary and "117" in block.summary
