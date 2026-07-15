"""Testes de introspecção dinâmica de key_metrics."""

from __future__ import annotations

import pytest

from orion_mcp_v3.public_chat.domain.intent_contract import EntityFilter, IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.key_metrics_introspection import (
    HeuristicStatus,
    build_dynamic_requirement,
    build_key_metrics_index,
    build_key_metrics_index_from_hits,
    dimensions_from_contract,
    find_key_metrics_source,
)
from orion_mcp_v3.public_chat.domain.knowledge import KnowledgeHit
from orion_mcp_v3.public_chat.tests.phase4.fixtures import load_maio_contract_fixture, maio_hit


def test_build_key_metrics_index_reads_meta_from_fixture() -> None:
    fixture = load_maio_contract_fixture()
    index = build_key_metrics_index(fixture["key_metrics"])

    assert len(index) >= 9
    dimensions = {entry.dimension for entry in index}
    assert "servico" in dimensions
    assert "produto" in dimensions
    assert "forma_pagamento" in dimensions


def test_build_key_metrics_index_from_hits_preserves_origin_metadata() -> None:
    fixture = load_maio_contract_fixture()
    hit = KnowledgeHit(
        origin_id=33,
        context_key="sistema_background:fechamento_gerencial:faturamento_por_forma_pagamento:2026-05",
        category="Fechamento Gerencial",
        validated_answer="Faturamento por forma de pagamento em maio.",
        key_metrics={
            "faturamento_por_tipo_de_pagamento": fixture["key_metrics"][
                "faturamento_por_tipo_de_pagamento"
            ],
        },
        score=0.354322,
    )

    index = build_key_metrics_index_from_hits((hit,))

    assert len(index) == 1
    assert index[0].key == "faturamento_por_tipo_de_pagamento"
    assert index[0].origin_id == 33
    assert index[0].context_key == hit.context_key


def test_find_key_metrics_source_resolves_servico_without_llm() -> None:
    hit = maio_hit()
    index = build_key_metrics_index(hit.key_metrics)
    match = find_key_metrics_source(index, dimension="servico", message="maior servico em maio")

    assert match.status == HeuristicStatus.RESOLVED
    assert match.entry is not None
    assert match.entry.key == "producao_por_servico"
    assert match.match_method is not None


def test_find_key_metrics_source_prefers_canonical_revenue_for_period_total() -> None:
    hit = maio_hit()
    index = build_key_metrics_index(
        {
            "parcelamento_de_cartao": hit.key_metrics["parcelamento_de_cartao"],
            "faturamento_por_tipo_de_venda": hit.key_metrics["faturamento_por_tipo_de_venda"],
            "faturamento_por_tipo_de_pagamento": hit.key_metrics["faturamento_por_tipo_de_pagamento"],
        }
    )

    match = find_key_metrics_source(
        index,
        dimension="periodo",
        metric_kind="faturamento",
        message="qual o faturamento em maio de 2026?",
    )

    assert match.status == HeuristicStatus.RESOLVED
    assert match.entry is not None
    assert match.entry.key == "faturamento_por_tipo_de_venda"


def test_find_key_metrics_source_resolves_parcelas_to_parcelamento_de_cartao() -> None:
    fixture = load_maio_contract_fixture()
    index = build_key_metrics_index(
        {
            "parcelamento_de_cartao": fixture["key_metrics"]["parcelamento_de_cartao"],
            "faturamento_por_tipo_de_pagamento": fixture["key_metrics"][
                "faturamento_por_tipo_de_pagamento"
            ],
        }
    )

    match = find_key_metrics_source(
        index,
        dimension="parcelas",
        metric_kind="faturamento",
        entity="5X",
        message="cartão de crédito em 5x em abril de 2026",
    )

    assert match.status == HeuristicStatus.RESOLVED
    assert match.entry is not None
    assert match.entry.key == "parcelamento_de_cartao"


def test_dimensions_from_contract_prefers_parcelas_over_forma_pagamento() -> None:
    contract = IntentContract(
        intent="consulta_metrica",
        metric="faturamento",
        period="2026-04",
        dimension="forma_pagamento",
        entity_filters=(EntityFilter(dimension="parcelas", value="5X", match="contains"),),
    )

    dims = dimensions_from_contract(
        contract,
        "qual o total de vendas com pagamento em cartão de credito em 5x em abril de 2026?",
    )

    assert dims[0] == "parcelas"
    assert "forma_pagamento" not in dims


def test_build_dynamic_requirement_uses_parcel_entity_for_parcelas_dimension() -> None:
    fixture = load_maio_contract_fixture()
    index = build_key_metrics_index({"parcelamento_de_cartao": fixture["key_metrics"]["parcelamento_de_cartao"]})
    entry = index[0]
    contract = IntentContract(
        intent="consulta_metrica",
        metric="faturamento",
        period="2026-04",
        dimension="parcelas",
        entity_filters=(
            EntityFilter(dimension="forma_pagamento", value="cartão de crédito", match="contains"),
            EntityFilter(dimension="parcelas", value="5x", match="contains"),
        ),
    )

    requirement = build_dynamic_requirement(entry, contract=contract, message="cartão de crédito em 5x")

    assert requirement.matched_key == "parcelamento_de_cartao"
    assert requirement.entity == "5X"


def test_find_key_metrics_source_segment_match_tipo_de_venda() -> None:
    hit = maio_hit()
    index = build_key_metrics_index(hit.key_metrics)
    match = find_key_metrics_source(index, dimension="tipo_de_venda", message="faturamento por tipo de venda")

    assert match.status == HeuristicStatus.RESOLVED
    assert match.entry is not None
    assert match.entry.key == "faturamento_por_tipo_de_venda"


def test_dimensions_from_contract_detects_servico_and_produto() -> None:
    contract = IntentContract(
        intent="consulta_metrica",
        metric="faturamento",
        period="2026-05",
        dimension="servico",
        operation=PublicOperationType.RANKING_DESC.value,
    )
    dims = dimensions_from_contract(contract, "quais servicos e produtos venderam mais?")

    assert dims == ("servico", "produto")


def test_build_dynamic_requirement_uses_percentual_for_share_metric() -> None:
    hit = maio_hit()
    index = build_key_metrics_index(hit.key_metrics)
    payment = next(entry for entry in index if entry.key == "faturamento_por_tipo_de_pagamento")
    contract = IntentContract(
        intent="consulta_metrica",
        metric="share",
        period="2026-05",
        dimension="forma_pagamento",
        entity_filters=(EntityFilter(dimension="forma_pagamento", value="PIX"),),
    )
    requirement = build_dynamic_requirement(payment, contract=contract)

    assert requirement.semantics.key_metrics_value_field == "percentual"
    assert requirement.fact_key == "dynamic:faturamento_por_tipo_de_pagamento@pix"
    assert requirement.entity == "PIX"
