"""Constantes compartilhadas entre parsing e merging de relatórios de e-mail."""

from __future__ import annotations

# Títulos canônicos de seção do fechamento gerencial (normalizados com casefold + espaço único).
FECHAMENTO_SECTION_TITLES: frozenset[str] = frozenset(
    {
        "faturamento por tipo de pagamento",
        "faturamento por tipo de venda",
        "produção por serviço",
        "producao por servico",
        "parcelamento de cartão",
        "parcelamento de cartao",
        "taxas de cartão de crédito",
        "taxas de cartao de credito",
    }
)

# Prefixos que indicam item de métrica fora da seção correta (LLM misturou blocos).
CROSS_SECTION_PREFIXES: tuple[str, ...] = (
    "faturamento por ",
    "faturamento e comissão",
    "faturamento e comissao",
    "produção por ",
    "producao por ",
    "parcelamento de ",
    "taxas de ",
)
