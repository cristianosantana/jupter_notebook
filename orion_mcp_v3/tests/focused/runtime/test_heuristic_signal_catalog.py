from __future__ import annotations

from orion_mcp_v3.runtime.heuristic_signal_catalog import extract_heuristic_signals


def test_regex_catalog_exposes_generic_comparative_signals() -> None:
    catalog = extract_heuristic_signals(
        "quero comparar março e abril de 2026 por vendedor, quem teve queda nas vendas?"
    )

    labels = {(signal.kind, signal.label) for signal in catalog.signals}
    assert ("intent_signal", "comparative") in labels
    assert ("intent_signal", "temporal") in labels
    assert ("metric_signal", "sales") in labels
    assert ("dimension_signal", "seller") in labels
    assert ("operation_signal", "delta") in labels
    assert catalog.as_prompt_dict()[0]["source"] == "regex"


def test_regex_catalog_adds_explicit_period_signal() -> None:
    catalog = extract_heuristic_signals("faturamento entre janeiro e abriu de 2026")

    assert any(
        signal.kind == "time_signal"
        and signal.label == "explicit_month_range"
        and signal.matched_text == "2026-01-01/2026-04-30"
        for signal in catalog.signals
    )
