"""Cognitive Foundation — CognitivePlan, padrões, IntentResolver, mapeamento AttentionPolicy."""

from __future__ import annotations

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
