"""Testes cruzados produtor/consumidor do contrato key_metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orion_mcp_v3.public_chat.domain.key_metrics_contract import collect_index_identities, enrich_key_metrics
from orion_mcp_v3.public_chat.domain.key_metrics_introspection import (
    HeuristicStatus,
    build_key_metrics_index,
    find_key_metrics_source,
)
from orion_mcp_v3.public_chat.domain.intent_contract import IntentContract
from orion_mcp_v3.public_chat.tests.phase4.fixtures import load_maio_contract_fixture

_FIXTURE_PATH = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "fechamento_maio_2026_key_metrics.json"


def test_fixture_exists_and_has_nine_indices() -> None:
    fixture = json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))
    assert fixture["period"] == "2026-05"
    assert len(fixture["key_metrics"]) == 9


def test_no_index_identity_collisions_in_fixture() -> None:
    fixture = load_maio_contract_fixture()
    identities = collect_index_identities(fixture["key_metrics"])
    keys = [identity for _, identity in identities]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize(
    ("dimension", "expected_key"),
    [
        ("servico", "producao_por_servico"),
        ("produto", "producao_por_produto"),
        ("forma_pagamento", "faturamento_por_tipo_de_pagamento"),
        ("concessionaria", "faturamento_e_comissao_por_concessionaria"),
        ("tipo_de_venda", "faturamento_por_tipo_de_venda"),
    ],
)
def test_contract_matrix_resolves_index_by_dimension(dimension: str, expected_key: str) -> None:
    fixture = load_maio_contract_fixture()
    index = build_key_metrics_index(fixture["key_metrics"])
    meta = next(entry for entry in index if entry.key == expected_key)
    contract = IntentContract(
        intent="consulta_metrica",
        metric=meta.metric_kind,
        period=fixture["period"],
        dimension=dimension,
    )
    match = find_key_metrics_source(index, dimension=dimension, metric_kind=contract.metric)
    assert match.status == HeuristicStatus.RESOLVED
    assert match.entry is not None
    assert match.entry.key == expected_key


def test_enrich_key_metrics_wraps_legacy_array_with_meta() -> None:
    enriched = enrich_key_metrics(
        {
            "producao_por_servico": [
                {"rank": "1", "servico": "PPF FULL", "valor": "R$ 100,00", "percentual": "10%"},
            ]
        }
    )
    payload = enriched["producao_por_servico"]
    assert "_meta" in payload
    assert payload["_meta"]["dimension"] == "servico"
    assert len(payload["rows"]) == 1


def _flat_servico_map(count: int) -> dict[str, str]:
    return {
        f"SERVICO {index:02d}": f"R$ {(count - index + 1) * 1_000:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        for index in range(1, count + 1)
    }


def test_enrich_key_metrics_head_tail_for_large_flat_map() -> None:
    enriched = enrich_key_metrics(
        _flat_servico_map(25),
        metric_kind="producao",
        dimension="por_servico",
        theme="producao_por_servico",
    )
    payload = enriched["producao_por_servico"]
    assert payload["_meta"]["truncated_head_tail"] is True
    assert payload["_meta"]["total_original_rows"] == 25
    assert len(payload["rows"]) == 20
    assert payload["rows"][0]["servico"] == "SERVICO 01"
    assert payload["rows"][-1]["servico"] == "SERVICO 25"
    assert "_omitidos_centro" not in enriched
    assert "_omitidos_centro" not in payload


def test_enrich_key_metrics_keeps_all_rows_for_small_flat_map() -> None:
    enriched = enrich_key_metrics(
        _flat_servico_map(8),
        metric_kind="producao",
        dimension="por_servico",
        theme="producao_por_servico",
    )
    payload = enriched["producao_por_servico"]
    assert payload["_meta"]["truncated_head_tail"] is False
    assert payload["_meta"]["total_original_rows"] == 8
    assert len(payload["rows"]) == 8


def test_enrich_key_metrics_wraps_legacy_polluted_flat_map_with_meta() -> None:
    flat = {
        "GWM BAMAQ": "R$ 43.584,46 (11,55%)",
        "SAITAMA - HONDA": "R$ 36.755,90 (9,74%)",
        "_omitidos_centro": "1 entradas omitidas (dados intermediarios)",
        "... Omitidas 11 linha(s) intermediárias. Exibindo os 10 piores resultados abaixo ...": None,
    }
    enriched = enrich_key_metrics(
        flat,
        metric_kind="comissao",
        dimension="por_concessionaria",
        theme="comissao_por_concessionaria",
    )
    assert "faturamento_e_comissao_por_concessionaria" in enriched
    payload = enriched["faturamento_e_comissao_por_concessionaria"]
    assert payload["_meta"]["dimension"] == "concessionaria"
    assert payload["_meta"]["metric_kind"] == "commission"
    rows = payload["rows"]
    assert rows[0]["concessionaria"] == "GWM BAMAQ"
    assert len(rows) == 2
    assert "_omitidos_centro" not in enriched


def test_enrich_key_metrics_wraps_root_flat_map_faturamento_por_forma_pagamento() -> None:
    flat = {
        "Cartão de Crédito": "R$ 1.271.748,02 (47,25%)",
        "PIX": "R$ 394.350,70 (14,65%)",
    }
    enriched = enrich_key_metrics(
        flat,
        metric_kind="faturamento",
        dimension="por_forma_pagamento",
        theme="faturamento_por_forma_pagamento",
    )
    key = "faturamento_por_tipo_de_pagamento"
    assert key in enriched
    assert enriched[key]["_meta"]["dimension"] == "forma_pagamento"
    index = build_key_metrics_index(enriched)
    match = find_key_metrics_source(
        index,
        dimension="forma_pagamento",
        metric_kind="revenue",
    )
    assert match.status == HeuristicStatus.RESOLVED


def test_find_key_metrics_source_resolves_comissoes_plural_metric_kind() -> None:
    enriched = enrich_key_metrics(
        {
            "GWM BAMAQ": "R$ 43.584,46 (11,55%)",
            "SAITAMA - HONDA": "R$ 36.755,90 (9,74%)",
        },
        metric_kind="comissao",
        dimension="por_concessionaria",
        theme="comissao_por_concessionaria",
    )
    index = build_key_metrics_index(enriched)
    match = find_key_metrics_source(
        index,
        dimension="concessionaria",
        metric_kind="comissoes",
    )
    assert match.status == HeuristicStatus.RESOLVED
    assert match.entry is not None
    assert match.entry.key == "faturamento_e_comissao_por_concessionaria"


def test_enrich_key_metrics_wraps_tipo_os_table() -> None:
    flat = {
        "GWM BAMAQ": "venda normal: R$ 43.584,46 | financiamento: R$ 0,00 | total comissão: R$ 43.584,46",
    }
    enriched = enrich_key_metrics(
        flat,
        metric_kind="comissao",
        dimension="por_concessionaria_tipo_os",
        theme="comissao_por_concessionaria_tipo_os",
    )
    key = "comissao_por_tipo_de_os_por_concessionaria"
    assert key in enriched
    assert enriched[key]["_meta"]["schema"] == "table"
    assert "table_rows_sample" in enriched[key]
