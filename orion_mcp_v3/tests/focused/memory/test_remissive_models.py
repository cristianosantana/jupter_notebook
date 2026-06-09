from __future__ import annotations

from orion_mcp_v3.memory.remissive_models import build_context_key


def test_build_context_key_slugifies_semantic_fields_with_period() -> None:
    assert (
        build_context_key(
            "sistema_background",
            "Fechamento Gerencial",
            "Comissão por Concessionária",
            "2025-08",
        )
        == "sistema_background:fechamento_gerencial:comissao_por_concessionaria:2025-08"
    )


def test_build_context_key_is_stable_for_repeated_semantic_fields() -> None:
    first = build_context_key(
        "sistema_background",
        "Formas de Pagamento!",
        "Dominância do Cartão de Crédito",
        "2025 Q3",
    )
    second = build_context_key(
        "sistema_background",
        "Formas de Pagamento!",
        "Dominância do Cartão de Crédito",
        "2025 Q3",
    )

    assert first == second
    assert first == "sistema_background:formas_de_pagamento:dominancia_do_cartao_de_credito:2025-q3"


def test_build_context_key_omits_empty_period() -> None:
    assert (
        build_context_key("sistema_background", "Performance", "Taxa cartão BH estética", None)
        == "sistema_background:performance:taxa_cartao_bh_estetica"
    )
