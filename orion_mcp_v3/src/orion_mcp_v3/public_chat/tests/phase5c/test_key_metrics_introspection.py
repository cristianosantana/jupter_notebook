"""Testes de introspecção dinâmica de key_metrics."""

from __future__ import annotations

import pytest

from orion_mcp_v3.public_chat.domain.intent_contract import EntityFilter, IntentContract, PublicOperationType
from orion_mcp_v3.public_chat.domain.key_metrics_introspection import (
    HeuristicStatus,
    build_dynamic_requirement,
    build_key_metrics_index,
    dimensions_from_contract,
    find_key_metrics_source,
)
from orion_mcp_v3.public_chat.tests.phase4.fixtures import load_maio_contract_fixture, maio_hit


def test_build_key_metrics_index_reads_meta_from_fixture() -> None:
    fixture = load_maio_contract_fixture()
    index = build_key_metrics_index(fixture["key_metrics"])

    assert len(index) >= 9
    dimensions = {entry.dimension for entry in index}
    assert "servico" in dimensions
    assert "produto" in dimensions
    assert "forma_pagamento" in dimensions


def test_find_key_metrics_source_resolves_servico_without_llm() -> None:
    hit = maio_hit()
    index = build_key_metrics_index(hit.key_metrics)
    match = find_key_metrics_source(index, dimension="servico", message="maior servico em maio")

    assert match.status == HeuristicStatus.RESOLVED
    assert match.entry is not None
    assert match.entry.key == "producao_por_servico"
    assert match.match_method is not None


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
    assert requirement.fact_key == "dynamic:faturamento_por_tipo_de_pagamento"
