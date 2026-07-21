"""Canonicalização de key_metrics na destilação — dimensões compostas e drift."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

import pytest

from orion_mcp_v3.public_chat.domain.key_metrics_contract import enrich_key_metrics
from orion_mcp_v3.public_chat.domain.key_metrics_reader import rows_from_key_metrics_entry

SCRIPTS = Path(__file__).resolve().parents[3] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# Isola fingerprints de teste do arquivo de runtime
os.environ.setdefault(
    "ORION_KEY_METRICS_SCHEMA_FINGERPRINTS",
    str(Path(__file__).resolve().parent / "_test_schema_fingerprints.json"),
)

from distillery.field_parsers import mapping
from distillery.payload_parser import parse_distillation_payload
from distillery.prompt_builder import build_distillation_prompt
from distillery.schema_fingerprint import (
    SchemaFingerprintStore,
    fingerprint_key_metrics,
)
from normalize_key_metrics_legacy import normalize_table_line
from orion_mcp_v3.memory.remissive_models import RemissiveConversationWindow


def test_prompt_requires_table_schema_for_two_axis_dimensions() -> None:
    prompt = build_distillation_prompt(
        [
            RemissiveConversationWindow(
                session_id="s1",
                user_id="sistema_background",
                messages=[{"role": "user", "content": "fechamento"}],
                indexed_turns=[],
            )
        ]
    )
    assert '"schema": "table"' in prompt or '"schema":"table"' in prompt
    assert "por_concessionaria_tipo_os" in prompt
    assert "PROIBIDO: embutir sub-valores como texto livre" in prompt
    assert '"rows"' in prompt


def test_mapping_formats_composite_list_item_as_deterministic_string() -> None:
    raw = {
        "key_metrics": [
            {
                "label": "GWM BAMAQ",
                "venda_normal": "R$ 43.584,46",
                "financiamento": "R$ 0,00",
                "total_comissao": "R$ 43.584,46",
            }
        ]
    }
    result = mapping(raw, "key_metrics")
    assert "gwm_bamaq" in result
    assert isinstance(result["gwm_bamaq"], str)
    assert "{" not in result["gwm_bamaq"]
    assert "financiamento: R$ 0,00" in result["gwm_bamaq"]
    assert "venda_normal: R$ 43.584,46" in result["gwm_bamaq"]


def test_mapping_formats_nested_dict_values_in_flat_map() -> None:
    raw = {
        "key_metrics": {
            "GWM BAMAQ": {
                "venda_normal": "R$ 43.584,46",
                "financiamento": "R$ 0,00",
            }
        }
    }
    result = mapping(raw, "key_metrics")
    assert isinstance(result["GWM BAMAQ"], str)
    assert "financiamento: R$ 0,00" in result["GWM BAMAQ"]
    assert not isinstance(result["GWM BAMAQ"], dict)


def test_mapping_preserves_meta_and_rows_canonical_shape() -> None:
    raw = {
        "key_metrics": {
            "_meta": {
                "schema": "table",
                "entity_field": "concessionaria",
                "columns": ["venda_normal", "financiamento", "total_comissao"],
            },
            "rows": [
                {
                    "concessionaria": "GWM BAMAQ",
                    "venda_normal": "R$ 43.584,46",
                    "financiamento": "R$ 0,00",
                    "total_comissao": "R$ 43.584,46",
                }
            ],
        }
    }
    result = mapping(raw, "key_metrics")
    assert "_meta" in result
    assert result["_meta"]["schema"] == "table"
    assert len(result["rows"]) == 1
    assert result["rows"][0]["concessionaria"] == "GWM BAMAQ"


def test_enrich_raises_on_nested_dict_table_value() -> None:
    with pytest.raises(ValueError, match="valor estruturado nao serializado"):
        enrich_key_metrics(
            {
                "GWM BAMAQ": {
                    "venda_normal": "R$ 43.584,46",
                    "financiamento": "R$ 0,00",
                }
            },
            metric_kind="comissao",
            dimension="por_concessionaria_tipo_os",
            theme="comissao_por_concessionaria_tipo_os",
        )


def test_enrich_wraps_canonical_rows_without_python_repr() -> None:
    enriched = enrich_key_metrics(
        {
            "_meta": {
                "schema": "table",
                "entity_field": "concessionaria",
                "columns": ["venda_normal", "financiamento", "total_comissao"],
            },
            "rows": [
                {
                    "concessionaria": "GWM BAMAQ",
                    "venda_normal": "R$ 43.584,46",
                    "financiamento": "R$ 0,00",
                    "total_comissao": "R$ 43.584,46",
                }
            ],
        },
        metric_kind="comissao",
        dimension="por_concessionaria_tipo_os",
        theme="comissao_por_concessionaria_tipo_os",
    )
    key = "comissao_por_tipo_de_os_por_concessionaria"
    assert key in enriched
    payload = enriched[key]
    assert payload["_meta"]["schema"] == "table"
    assert "rows" in payload
    sample = payload.get("table_rows_sample") or []
    joined = " | ".join(sample) if sample else json.dumps(payload["rows"], ensure_ascii=False)
    assert "{'" not in joined
    assert "venda_normal" in joined or "R$ 43.584,46" in joined

    rows = rows_from_key_metrics_entry(key, payload)
    assert any(row.value == 0.0 for row in rows)
    assert any(abs(row.value - 43584.46) < 0.01 for row in rows)


def test_parse_composite_list_does_not_persist_python_dict_repr() -> None:
    batch = parse_distillation_payload(
        json.dumps(
            {
                "knowledge": [
                    {
                        "user_id": "sistema_background",
                        "category": "Fechamento Gerencial",
                        "theme": "comissao_por_concessionaria_tipo_os",
                        "metric_kind": "comissao",
                        "dimension": "por_concessionaria_tipo_os",
                        "periodo": "2026-05",
                        "validated_answer": (
                            "Comissao por concessionaria e tipo de OS em maio 2026 "
                            "com detalhamento completo de venda normal e financiamento."
                        ),
                        "recent_questions": [
                            "Qual concessionaria teve mais comissao por tipo de OS?"
                        ],
                        "key_metrics": [
                            {
                                "label": "GWM BAMAQ",
                                "venda_normal": "R$ 43.584,46",
                                "financiamento": "R$ 0,00",
                                "total_comissao": "R$ 43.584,46",
                            }
                        ],
                        "index_questions": [
                            "qual concessionaria liderou comissao por tipo de OS?",
                            "qual teve menor comissao por tipo de OS?",
                            "qual percentual veio de financiamento?",
                            "GWM BAMAQ superou SAITAMA em comissao?",
                            "como ficou a comissao por tipo de OS em maio?",
                        ],
                        "confidence": "high",
                    }
                ],
                "essence": [],
            }
        )
    )
    assert len(batch.knowledge) == 1
    payload = batch.knowledge[0].key_metrics["comissao_por_tipo_de_os_por_concessionaria"]
    blob = json.dumps(payload, ensure_ascii=False)
    assert "{'" not in blob
    assert "venda_normal" in blob or "Venda" in blob or "R$ 43.584,46" in blob


def test_normalize_legacy_python_dict_repr_in_table_line() -> None:
    line = (
        "GWM BAMAQ | {'venda_normal': 'R$ 43.584,46', 'financiamento': 'R$ 0,00', "
        "'total_comissao': 'R$ 43.584,46'}"
    )
    fixed = normalize_table_line(line)
    assert "{'" not in fixed
    assert fixed.startswith("GWM BAMAQ | ")
    assert "financiamento: R$ 0,00" in fixed
    assert "venda_normal: R$ 43.584,46" in fixed


def test_schema_fingerprint_detects_drift(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    store = SchemaFingerprintStore(path=tmp_path / "fingerprints.json")
    first = {
        "comissao_por_tipo_de_os_por_concessionaria": {
            "_meta": {"schema": "table", "entity_field": "concessionaria"},
            "rows": [
                {
                    "concessionaria": "GWM BAMAQ",
                    "venda_normal": "R$ 1,00",
                    "financiamento": "R$ 0,00",
                }
            ],
        }
    }
    second = {
        "comissao_por_tipo_de_os_por_concessionaria": {
            "_meta": {"schema": "table", "entity_field": "concessionaria"},
            "table_rows_sample": [
                "GWM BAMAQ | Venda Normal: R$ 1,00 | Financiamento: R$ 0,00",
            ],
        }
    }
    assert fingerprint_key_metrics(first) != fingerprint_key_metrics(second)

    with caplog.at_level(logging.WARNING):
        store.check_and_update(
            theme="comissao_por_concessionaria_tipo_os",
            dimension="por_concessionaria_tipo_os",
            key_metrics=first,
        )
        store.check_and_update(
            theme="comissao_por_concessionaria_tipo_os",
            dimension="por_concessionaria_tipo_os",
            key_metrics=second,
        )
    assert any("schema drift" in record.message.lower() for record in caplog.records)
