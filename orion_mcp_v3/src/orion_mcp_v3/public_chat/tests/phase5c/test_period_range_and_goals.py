"""Testes unitários: range expand + ops cumulative/time_series (sem BD)."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.analytical_plan import AnalyticalGoal, build_analytical_plan
from orion_mcp_v3.public_chat.domain.intent_contract import EntityFilter, IntentContract
from orion_mcp_v3.public_chat.domain.intent_heuristics import apply_heuristic_enrichment
from orion_mcp_v3.public_chat.domain.intent_parser import extract_mentioned_periods
from orion_mcp_v3.public_chat.domain.period_selection import (
    expand_period_range,
    periods_from_contract,
)


def test_expand_period_range_inclusive() -> None:
    assert expand_period_range("2026-01", "2026-03") == (
        "2026-01",
        "2026-02",
        "2026-03",
    )


def test_extract_mentioned_periods_fills_range() -> None:
    assert extract_mentioned_periods("entre janeiro e maio de 2026") == (
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
    )


def test_extract_semestre() -> None:
    assert extract_mentioned_periods("1º semestre de 2026") == (
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
        "2026-06",
    )


def test_periods_from_contract_expands_endpoints() -> None:
    contract = IntentContract(
        intent="consulta_metrica",
        period="2026-01",
        entity_filters=(EntityFilter("periodo", "2026-05", "exact"),),
        confidence=1.0,
    )
    assert periods_from_contract(contract) == (
        "2026-01",
        "2026-02",
        "2026-03",
        "2026-04",
        "2026-05",
    )


def test_heuristic_time_series_and_cumulative() -> None:
    base = IntentContract(intent="consulta_metrica", confidence=0.9)
    ts = apply_heuristic_enrichment(
        base,
        "Em quais meses entre janeiro e abril de 2026 o Pix ultrapassou o Cartão?",
    )
    assert ts.operation == "time_series"
    cum = apply_heuristic_enrichment(
        base,
        "Qual a diferença entre o total de comissão de janeiro a maio de 2026?",
    )
    assert cum.operation == "cumulative"


def test_analytical_plan_goals() -> None:
    ts = build_analytical_plan(
        IntentContract(intent="consulta_metrica", operation="time_series", period="2026-01", confidence=1.0)
    )
    assert ts.goal == AnalyticalGoal.TIME_SERIES
    cum = build_analytical_plan(
        IntentContract(intent="consulta_metrica", operation="cumulative", period="2026-01", confidence=1.0)
    )
    assert cum.goal == AnalyticalGoal.CUMULATIVE
