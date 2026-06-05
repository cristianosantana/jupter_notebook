"""Classificação leve do tipo de mensagem antes da estruturação de e-mail."""

from __future__ import annotations

import re
from typing import Literal

EmailMessageType = Literal["fechamento_gerencial", "ranking", "comparacao", "analise_unica", "conversacional"]

_FECHAMENTO_RX = re.compile(
    r"fechamento\s+gerencial|(?:\d+\s+template\(s\))|##\s*Faturamento por tipo de pagamento",
    re.I,
)
_COMPARACAO_RX = re.compile(r"queda|aumento|delta|varia[cç][aã]o|subiu|caiu|versus|compara[cç]", re.I)
_RANKING_RX = re.compile(r"ranking|top\s+\d+|posi[cç][aã]o|^\s*1\.\s+.+?R\$", re.I | re.M)
_MONEY_RX = re.compile(r"R\$\s*[\d.,]+")


def classify_message(body: str) -> EmailMessageType:
    """Classifica a resposta textual antes de acionar prompts específicos."""

    text = body or ""
    if _FECHAMENTO_RX.search(text):
        return "fechamento_gerencial"
    if _COMPARACAO_RX.search(text):
        return "comparacao"
    if _RANKING_RX.search(text):
        return "ranking"
    if _MONEY_RX.search(text):
        return "analise_unica"
    return "conversacional"
