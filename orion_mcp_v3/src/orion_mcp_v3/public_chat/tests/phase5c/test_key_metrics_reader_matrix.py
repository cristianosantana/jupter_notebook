"""Testes de parsing matricial (subdimension × dimension) em key_metrics_reader."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.key_metrics_reader import (
    lookup_entity,
    normalize_key_metrics_entry,
    rows_from_key_metrics_entry,
    rows_from_table_sample,
)


def test_parse_matrix_table_line_expands_columns_with_zero():
    raw = {
        "_meta": {
            "dimension": "tipo_os",
            "entity_field": "tipo_os",
            "value_field": "valor_comissao",
            "metric_kind": "commission",
            "schema": "table",
            "subdimension": "concessionaria",
        },
        "table_rows_sample": [
            "GWM BAMAQ | Venda Normal: R$ 38.162,34 | Financiamento: R$ 0,00 | Total comissão: R$ 38.162,34",
            "SAITAMA - HONDA | Venda Normal: R$ 28.544,60 | Financiamento: R$ 7.251,00 | Total comissão: R$ 35.795,60",
        ],
    }
    rows = rows_from_key_metrics_entry("comissao_por_tipo_de_os_por_concessionaria", raw)

    fin = lookup_entity(rows, "Financiamento")
    assert fin is not None
    assert fin.value == 0.0
    assert "gwm bamaq" in fin.label.lower()
    assert "financiamento" in fin.label.lower()

    vn = lookup_entity(rows, "Venda Normal")
    assert vn is not None
    assert vn.value == 38162.34
    assert "gwm bamaq" in vn.label.lower()


def test_parse_matrix_without_column_labels_uses_position():
    raw = {
        "_meta": {
            "dimension": "tipo_os",
            "subdimension": "concessionaria",
            "schema": "table",
        },
        "table_rows_sample": [
            "GWM BAMAQ | R$ 39.416,00 | R$ 0,00 | R$ 39.416,00",
        ],
    }
    rows = rows_from_key_metrics_entry("comissao_por_tipo_de_os_por_concessionaria", raw)

    assert len(rows) >= 2
    fin_rows = [row for row in rows if "financiamento" in row.label.lower() or row.value == 0.0]
    assert any(row.value == 0.0 for row in fin_rows)


def test_simple_table_without_subdimension_unchanged():
    sample = ["PIX: R$ 100,00", "Cheque: R$ 0,00"]
    rows = rows_from_table_sample(sample)
    cheque = lookup_entity(rows, "Cheque")
    assert cheque is not None
    assert cheque.value == 0.0


def test_normalize_entry_matrix_shape():
    raw = {
        "_meta": {"subdimension": "concessionaria", "schema": "table"},
        "table_rows_sample": ["GWM BAMAQ | Financiamento: R$ 0,00"],
    }
    entry = normalize_key_metrics_entry("comissao_por_tipo_de_os_por_concessionaria", raw)
    assert entry.shape == "table"
    assert len(entry.rows) == 1
    assert entry.rows[0].value == 0.0
