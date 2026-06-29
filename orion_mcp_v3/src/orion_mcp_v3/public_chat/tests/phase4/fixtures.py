"""Fixtures partilhadas da Fase 4."""

from __future__ import annotations

import json
from pathlib import Path

from orion_mcp_v3.public_chat.domain.knowledge import KnowledgeHit

_FIXTURE_PATH = Path(__file__).resolve().parents[5] / "tests" / "fixtures" / "fechamento_maio_2026_key_metrics.json"


def load_maio_contract_fixture() -> dict:
    return json.loads(_FIXTURE_PATH.read_text(encoding="utf-8"))


FECHAMENTO_MARCO_2026 = """
Formas de pagamento — Total: R$ 2.713.158,18.

Cartão de Crédito R$ 1.352.045,28
Concessionária R$ 886.921,02
PIX R$ 399.819,98
Dinheiro R$ 55.179,90
Parcelamento R$ 15.502,00
Depósito Bancário R$ 3.690,00
Cheque R$ 0,00
Permuta R$ 0,00

Tipos de venda — Total: R$ 2.713.158,18.

Venda Normal R$ 1.651.289,15
Venda Concessionária R$ 886.921,02

Produção por serviço — Total: R$ 2.563.819,17.

PPF REGENERATIVO - FULL R$ 442.570,00
"""

_MARCH_PAYMENTS = [
    {"rank": "1", "tipo": "Cartão de Crédito", "valor": "R$ 1.352.045,28", "percentual": "49,83%"},
    {"rank": "2", "tipo": "Concessionária", "valor": "R$ 886.921,02", "percentual": "32,69%"},
    {"rank": "3", "tipo": "PIX", "valor": "R$ 399.819,98", "percentual": "14,74%"},
    {"rank": "4", "tipo": "Dinheiro", "valor": "R$ 55.179,90", "percentual": "2,03%"},
    {"rank": "5", "tipo": "Parcelamento", "valor": "R$ 15.502,00", "percentual": "0,57%"},
    {"rank": "6", "tipo": "Depósito Bancário", "valor": "R$ 3.690,00", "percentual": "0,14%"},
    {"rank": "7", "tipo": "Cheque", "valor": "R$ 0,00", "percentual": "0,00%"},
    {"rank": "8", "tipo": "Permuta", "valor": "R$ 0,00", "percentual": "0,00%"},
]

MAIO_2026_KEY_METRICS = load_maio_contract_fixture()["key_metrics"]


def maio_hit(*, origin_id: int = 1) -> KnowledgeHit:
    fixture = load_maio_contract_fixture()
    return KnowledgeHit(
        origin_id=origin_id,
        context_key=fixture["context_key"],
        category="fechamento gerencial",
        validated_answer="Detalhe por seção do fechamento gerencial...",
        key_metrics=fixture["key_metrics"],
        score=0.85,
    )


def march_hit(*, origin_id: int = 4) -> KnowledgeHit:
    return KnowledgeHit(
        origin_id=origin_id,
        context_key="sistema_background:fechamento_gerencial_mensal:marco_2026:2026-03-01-to-2026-03-31",
        category="fechamento_gerencial_mensal",
        validated_answer=FECHAMENTO_MARCO_2026.strip(),
        key_metrics={
            "faturamento_liquido": 2713158.18,
            "faturamento_por_tipo_de_pagamento": {
                "_meta": {
                    "dimension": "forma_pagamento",
                    "entity_field": "tipo",
                    "value_field": "valor",
                    "metric_kind": "revenue",
                    "schema": "ranked_list",
                },
                "rows": _MARCH_PAYMENTS,
            },
        },
        score=0.1,
    )


def other_month_hit(*, origin_id: int, month_slug: str, period: str) -> KnowledgeHit:
    return KnowledgeHit(
        origin_id=origin_id,
        context_key=f"sistema_background:fechamento_gerencial_mensal:{month_slug}:{period}",
        category="fechamento_gerencial_mensal",
        validated_answer=f"Faturamento líquido R$ 2.000.000,00 em {month_slug}.",
        key_metrics={"faturamento_liquido": 2000000.0},
        score=0.5,
    )
