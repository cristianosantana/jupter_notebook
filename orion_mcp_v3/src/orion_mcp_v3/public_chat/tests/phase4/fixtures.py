"""Fixtures partilhadas da Fase 4."""

from __future__ import annotations

from orion_mcp_v3.public_chat.domain.knowledge import KnowledgeHit

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


def march_hit(*, origin_id: int = 4) -> KnowledgeHit:
    return KnowledgeHit(
        origin_id=origin_id,
        context_key="sistema_background:fechamento_gerencial_mensal:marco_2026:2026-03-01-to-2026-03-31",
        category="fechamento_gerencial_mensal",
        validated_answer=FECHAMENTO_MARCO_2026.strip(),
        key_metrics={"faturamento_liquido": 2713158.18},
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
