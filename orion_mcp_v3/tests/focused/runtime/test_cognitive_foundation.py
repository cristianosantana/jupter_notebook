"""Cognitive Foundation — CognitivePlan, padrões, IntentResolver, mapeamento AttentionPolicy."""

from __future__ import annotations

import calendar
from datetime import date, timedelta

import pytest

from orion_mcp_v3.contracts.cognitive_plan import AttentionProfile, IntentType
from orion_mcp_v3.contracts.query_plan import RetrievalStrategy
from orion_mcp_v3.runtime import map_attention_profile_to_policy, policy_shares
from orion_mcp_v3.runtime.attention_policy import AttentionPolicy
from orion_mcp_v3.runtime.intent_resolver import IntentResolver


def test_map_attention_profile_covers_all_profiles() -> None:
    for ap in AttentionProfile:
        pol = map_attention_profile_to_policy(ap)
        assert isinstance(pol, AttentionPolicy)
        shares = policy_shares(pol)
        assert abs(shares.system + shares.essence + shares.free - 1.0) < 0.01


def test_resolve_analytics_for_forma_pagamento_without_faturamento_keyword() -> None:
    """Perguntas só com 'forma de pagamento' devem activar broker (templates de caixas)."""
    p = IntentResolver().resolve(
        "Qual forma de pagamento domina entre janeiro e abril de 2026?",
    )
    assert p.needs_analytics is True
    assert p.intent_type == IntentType.ANALYTICAL
    assert p.needs_temporal_context is True
    assert p.time_scope == "2026-01-01/2026-04-30"
    assert p.hints["date_from"] == "2026-01-01"
    assert p.hints["date_to"] == "2026-04-30"
    assert p.hints["explicit_period"] == {
        "date_from": "2026-01-01",
        "date_to": "2026-04-30",
    }


def test_resolve_explicit_single_month_period() -> None:
    p = IntentResolver().resolve("Mostre o faturamento em março de 2026")
    assert p.needs_temporal_context is True
    assert p.time_scope == "2026-03-01/2026-03-31"
    assert p.hints["period_source"] == "explicit_month"


@pytest.mark.parametrize(
    ("text", "expected_from", "expected_to", "source"),
    [
        (
            "faturamento de 01/01/2026 a 30/04/2026",
            "2026-01-01",
            "2026-04-30",
            "explicit_date_range",
        ),
        (
            "faturamento de 2026-01-01 até 2026-04-30",
            "2026-01-01",
            "2026-04-30",
            "explicit_iso_range",
        ),
        (
            "faturamento de jan/2026 até abr/2026",
            "2026-01-01",
            "2026-04-30",
            "explicit_month_abbrev_range",
        ),
        (
            "faturamento de jan a abr/26",
            "2026-01-01",
            "2026-04-30",
            "explicit_month_abbrev_range",
        ),
        (
            "faturamento Q1 2026",
            "2026-01-01",
            "2026-03-31",
            "explicit_quarter",
        ),
        (
            "faturamento no 1º trimestre de 2026",
            "2026-01-01",
            "2026-03-31",
            "explicit_quarter",
        ),
        (
            "faturamento entre 10 e 20 de abril de 2026",
            "2026-04-10",
            "2026-04-20",
            "explicit_day_month_range",
        ),
    ],
)
def test_resolve_explicit_date_period_variants(
    text: str,
    expected_from: str,
    expected_to: str,
    source: str,
) -> None:
    p = IntentResolver().resolve(text)
    assert p.needs_temporal_context is True
    assert p.time_scope == f"{expected_from}/{expected_to}"
    assert p.hints["date_from"] == expected_from
    assert p.hints["date_to"] == expected_to
    assert p.hints["period_source"] == source


def test_resolve_relative_current_month() -> None:
    today = date.today()
    expected_from = date(today.year, today.month, 1).isoformat()
    expected_to = date(
        today.year,
        today.month,
        calendar.monthrange(today.year, today.month)[1],
    ).isoformat()
    p = IntentResolver().resolve("mostre o faturamento do mês atual")
    assert p.time_scope == f"{expected_from}/{expected_to}"
    assert p.hints["period_source"] == "relative_current_month"


def test_resolve_relative_last_year() -> None:
    year = date.today().year - 1
    p = IntentResolver().resolve("qual o faturamento do ano passado?")
    assert p.time_scope == f"{year}-01-01/{year}-12-31"
    assert p.hints["period_source"] == "relative_last_year"


def test_resolve_relative_last_90_days() -> None:
    today = date.today()
    expected_from = (today - timedelta(days=89)).isoformat()
    p = IntentResolver().resolve("faturamento dos últimos 90 dias")
    assert p.time_scope == f"{expected_from}/{today.isoformat()}"
    assert p.hints["period_source"] == "relative_last_days"


def test_resolve_analytical_temporal() -> None:
    r = IntentResolver()
    p = r.resolve("mostre o faturamento dos últimos 3 meses")
    assert p.intent_type == IntentType.ANALYTICAL
    assert p.needs_analytics is True
    assert p.needs_temporal_context is True
    assert p.attention_profile == AttentionProfile.ANALYTICAL
    assert p.retrieval_strategy == RetrievalStrategy.BROKER_FANOUT


def test_resolve_recall() -> None:
    p = IntentResolver().resolve("o que falamos ontem?")
    assert p.intent_type == IntentType.RECALL
    assert p.needs_memory is True
    assert p.needs_analytics is False
    assert p.attention_profile == AttentionProfile.MEMORY_FOCUSED
    assert map_attention_profile_to_policy(p.attention_profile) == AttentionPolicy.MEMORY_FOCUSED


def test_resolve_comparative_and_analytics() -> None:
    p = IntentResolver().resolve("de novo o faturamento comparado ao mês passado")
    assert p.needs_comparison is True
    assert p.needs_analytics is True


def test_resolve_monitoring() -> None:
    p = IntentResolver().resolve("alerta se o ticket médio subiu")
    assert p.intent_type == IntentType.MONITORING
    assert map_attention_profile_to_policy(p.attention_profile) == AttentionPolicy.MONITORING


def test_resolve_execution() -> None:
    p = IntentResolver().resolve("executa o relatório de vendas")
    assert p.intent_type == IntentType.EXECUTION


def test_recent_context_influences_signals() -> None:
    p = IntentResolver().resolve(
        "resume",
        recent_context="top clientes por faturamento em janeiro",
    )
    assert p.needs_analytics is True
