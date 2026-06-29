"""
Catálogos de dimension e metric_kind — fonte de verdade para resolução.

Para adicionar um novo valor canônico: editar apenas este arquivo.
O parser e o prompt consomem os catálogos automaticamente — sem
necessidade de editar outras partes do código.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dimension
# ---------------------------------------------------------------------------

#: Slugs canônicos aceitos para o campo dimension.
DIMENSION_CANONICAL: frozenset[str] = frozenset({
    "total",
    "por_concessionaria",
    "por_concessionaria_tipo_os",
    "por_servico",
    "por_produto",
    "por_vendedor",
    "por_forma_pagamento",
    "por_tipo_venda",
    "por_numero_parcelas",
    "por_empresa",
    "por_regiao",
    "por_categoria",
    "por_periodo",
})

#: Mapeamento dimension → chave de índice canônica para key_metrics
DIMENSION_TO_INDEX_KEY: dict[str, str] = {
    "por_concessionaria": "comissao_por_concessionaria",
    "por_concessionaria_tipo_os": "comissao_por_tipo_de_os_por_concessionaria",
    "por_servico": "producao_por_servico",
    "por_produto": "producao_por_produto",
    "por_vendedor": "performance_por_vendedor",
    "por_forma_pagamento": "faturamento_por_tipo_de_pagamento",
    "por_tipo_venda": "faturamento_por_tipo_de_venda",
    "por_numero_parcelas": "parcelamento_de_cartao",
    "por_empresa": "taxas_cartao_credito",
}

#: Aliases que o LLM usa com frequência → slug canônico.
#: Adicionar novos aliases aqui sem alterar o parser.
DIMENSION_ALIASES: dict[str, str] = {
    # variações de por_numero_parcelas
    "por_parcela":             "por_numero_parcelas",
    "por_parcelas":            "por_numero_parcelas",
    "parcelas":                "por_numero_parcelas",
    "num_parcelas":            "por_numero_parcelas",
    "numero_parcelas":         "por_numero_parcelas",
    "quantidade_parcelas":     "por_numero_parcelas",
    # variações de por_empresa
    "por_empresa":             "por_empresa",
    "por_gateway":             "por_empresa",
    "por_operadora":           "por_empresa",
    "por_adquirente":          "por_empresa",
    "prestador":               "por_empresa",
    "empresa":                 "por_empresa",
    # variações de por_concessionaria_tipo_os
    "por_concessionaria_os":   "por_concessionaria_tipo_os",
    "por_concessionaria_tipo": "por_concessionaria_tipo_os",
    "por_conc_tipo_os":        "por_concessionaria_tipo_os",
    # variações de por_forma_pagamento
    "por_pagamento":           "por_forma_pagamento",
    "por_tipo_pagamento":      "por_forma_pagamento",
    "forma_pagamento":         "por_forma_pagamento",
    # variações de por_servico
    "por_tipo_servico":        "por_servico",
    "servico":                 "por_servico",
    # variações de por_tipo_venda
    "por_venda":               "por_tipo_venda",
    "tipo_venda":              "por_tipo_venda",
}

#: theme slug → dimension canônica.
#: Quando o LLM acerta o theme mas erra a dimension, este dict corrige.
#: Escala para qualquer período — lookup é pelo theme, não pelo context_key.
THEME_TO_DIMENSION: dict[str, str] = {
    "taxas_cartao_credito":                "por_empresa",
    "taxa_cartao_credito":                 "por_empresa",
    "comissao_por_concessionaria_tipo_os": "por_concessionaria_tipo_os",
    "parcelamento_cartao":                 "por_numero_parcelas",
    "parcelamento_por_cartao":             "por_numero_parcelas",
    "faturamento_por_forma_pagamento":     "por_forma_pagamento",
    "formas_de_pagamento":                 "por_forma_pagamento",
    "faturamento_por_tipo_venda":          "por_tipo_venda",
    "producao_por_servico":                "por_servico",
    "producao_por_produto":                "por_produto",
    "comissao_por_concessionaria":         "por_concessionaria",
    "faturamento_por_concessionaria":      "por_concessionaria",
}


# ---------------------------------------------------------------------------
# Metric kind
# ---------------------------------------------------------------------------

#: Slugs canônicos aceitos para o campo metric_kind.
METRIC_KIND_CANONICAL: frozenset[str] = frozenset({
    "faturamento",
    "comissao",
    "producao",
    "parcelamento",
    "taxa_cartao",
    "ticket_medio",
    "volume_vendas",
    "quantidade_servicos",
    "margem",
    "lucro",
    "custo",
    "investimento",
    "performance",
})

#: Aliases de metric_kind → canônico.
METRIC_KIND_ALIASES: dict[str, str] = {
    "receita":             "faturamento",
    "receita_liquida":     "faturamento",
    "faturamento_total":   "faturamento",
    "comissoes":           "comissao",
    "taxa":                "taxa_cartao",
    "taxas":               "taxa_cartao",
    "taxas_cartao":        "taxa_cartao",
    "producao_servico":    "producao",
    "producao_produto":    "producao",
    "parcelamento_cartao": "parcelamento",
}


# ---------------------------------------------------------------------------
# Resolvedores
# ---------------------------------------------------------------------------

def resolve_dimension(raw: str | None, *, theme: str | None = None) -> str | None:
    """
    Resolve dimension para slug canônico em três passos:

    1. theme → THEME_TO_DIMENSION (prioridade — escala para qualquer período)
    2. raw   → DIMENSION_ALIASES  (normaliza variações do LLM)
    3. raw   → DIMENSION_CANONICAL (valida se já é canônico)

    Não descarta o item se desconhecido — grava o valor recebido e loga warning.
    """
    # Passo 1: theme tem prioridade sobre o valor bruto
    if theme:
        slug = theme.strip().lower()
        if slug in THEME_TO_DIMENSION:
            resolved = THEME_TO_DIMENSION[slug]
            if raw and raw.strip().lower() != resolved:
                logger.info(
                    "dimension corrigida via theme '%s': '%s' → '%s'",
                    slug, raw, resolved,
                )
            return resolved

    if not raw:
        return None

    normalized = raw.strip().lower()

    # Passo 2: alias → canônico
    if normalized in DIMENSION_ALIASES:
        canonical = DIMENSION_ALIASES[normalized]
        logger.debug("dimension alias '%s' → '%s'", normalized, canonical)
        return canonical

    # Passo 3: já é canônico
    if normalized in DIMENSION_CANONICAL:
        return normalized

    logger.warning(
        "dimension desconhecida: '%s' (theme=%r) — gravando como recebido",
        raw, theme,
    )
    return normalized


def resolve_metric_kind(raw: str | None) -> str | None:
    """
    Resolve metric_kind para slug canônico via aliases e catálogo.

    Não descarta o item se desconhecido — grava o valor recebido e loga warning.
    """
    if not raw:
        return None
    normalized = raw.strip().lower()
    if normalized in METRIC_KIND_ALIASES:
        return METRIC_KIND_ALIASES[normalized]
    if normalized in METRIC_KIND_CANONICAL:
        return normalized
    logger.warning("metric_kind desconhecido: '%s' — gravando como recebido", raw)
    return normalized


def get_index_key_for_dimension(dimension: str | None) -> str | None:
    """
    Retorna a chave de índice canônica para uma determinada dimensão.
    
    Usado pelo key_metrics_contract para embrulhar mapas planos.
    """
    if not dimension:
        return None
    return DIMENSION_TO_INDEX_KEY.get(dimension)