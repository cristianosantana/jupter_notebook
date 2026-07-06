from __future__ import annotations

from orion_mcp_v3.public_chat.domain.query_normalizer import normalize_query_for_intent_cache


def test_normalize_query_for_intent_cache_ignores_accent_and_case() -> None:
    left = normalize_query_for_intent_cache(
        "Qual o total de vendas com pagamento em Cartão de Crédito em 10x?"
    )
    right = normalize_query_for_intent_cache(
        "qual o total de vendas com pagamento em cartao de credito em 10x?"
    )
    assert left == right
    assert left == "qual o total de vendas com pagamento em cartao de credito em 10x?"


def test_normalize_query_for_intent_cache_collapses_whitespace() -> None:
    assert normalize_query_for_intent_cache("  faturamento   maio  ") == "faturamento maio"
