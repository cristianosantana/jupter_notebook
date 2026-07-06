"""Testes de matching explícito de período em context_key."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.knowledge import ConhecimentoRecuperado, KnowledgeHit
from orion_mcp_v3.public_chat.domain.knowledge_scoper import scope_knowledge
from orion_mcp_v3.public_chat.domain.period_utils import period_in_context_key


def test_february_does_not_match_may_via_year_substring() -> None:
    may_key = (
        "sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-05"
    )
    assert period_in_context_key(may_key, "2026-02") is False
    assert period_in_context_key(may_key, "2026-05") is True


def test_february_does_not_match_january_period_token() -> None:
    jan_key = (
        "sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-01"
    )
    assert period_in_context_key(jan_key, "2026-02") is False
    assert period_in_context_key(jan_key, "2026-01") is True


def test_explicit_periodo_token_matches() -> None:
    feb_key = (
        "sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-02"
    )
    assert period_in_context_key(feb_key, "2026-02") is True


def test_suffix_yyyy_mm_matches() -> None:
    key = "sistema_background:fechamento_gerencial:faturamento_por_forma_pagamento:2026-02"
    assert period_in_context_key(key, "2026-02") is True
    assert period_in_context_key(key, "2026-05") is False


def test_range_context_key_matches_month() -> None:
    key = "sistema_background:fechamento_gerencial_mensal:marco_2026:2026-03-01-to-2026-03-31"
    assert period_in_context_key(key, "2026-03") is True
    assert period_in_context_key(key, "2026-02") is False


def test_scope_knowledge_february_excludes_other_months() -> None:
    hits = (
        KnowledgeHit(
            origin_id=10,
            context_key=(
                "sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-02"
            ),
            category="Fechamento Gerencial",
            validated_answer="Fev",
            key_metrics={},
        ),
        KnowledgeHit(
            origin_id=2,
            context_key=(
                "sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-01"
            ),
            category="Fechamento Gerencial",
            validated_answer="Jan",
            key_metrics={},
        ),
        KnowledgeHit(
            origin_id=34,
            context_key=(
                "sistema_background:fechamento_gerencial:faturamento_por_tipo_venda:periodo-2026-05"
            ),
            category="Fechamento Gerencial",
            validated_answer="Mai",
            key_metrics={},
        ),
    )
    scoped, degraded = scope_knowledge(ConhecimentoRecuperado(hits=hits), period="2026-02")
    assert degraded is False
    assert len(scoped.hits) == 1
    assert scoped.hits[0].origin_id == 10
