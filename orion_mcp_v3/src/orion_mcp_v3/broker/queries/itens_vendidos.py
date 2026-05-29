"""
itens_vendidos
===============

Responde:
    - Quais itens, produtos ou serviços mais venderam?
    - Quais itens mais faturaram no período?
    - Qual o ticket médio por item?
    - Qual a participação de cada item no faturamento?
    - Produto ou serviço gera mais receita?

Retorna:
    - periodo (VARCHAR, YYYY-MM)
    - categoria (VARCHAR: servico/produto)
    - item (VARCHAR)
    - quantidade_vendida (INT)
    - quantidade_os (INT)
    - vendas (DECIMAL)
    - ticket_medio_item (DECIMAL)
    - ticket_medio_os (DECIMAL)
    - percentual_faturamento (DECIMAL)

Parâmetros:
    - date_from (str): data início — default últimos 30 dias
    - date_to (str): data fim — default hoje

Granularidade: month (agregado por período/categoria/item)
Value key: vendas
Time key: periodo
Label key: item
"""

SQL = """\
SELECT
    periodo,
    categoria,
    item,
    SUM(quantidade_vendida) AS quantidade_vendida,
    COUNT(DISTINCT os_id) AS quantidade_os,
    ROUND(SUM(vendas), 2) AS vendas,
    ROUND(
        SUM(vendas) / SUM(quantidade_vendida),
        2
    ) AS ticket_medio_item,
    ROUND(
        SUM(vendas) / COUNT(DISTINCT os_id),
        2
    ) AS ticket_medio_os,
    ROUND(
        (
            SUM(vendas)
            / SUM(SUM(vendas)) OVER(PARTITION BY periodo)
        ) * 100,
        2
    ) AS percentual_faturamento
FROM (
    SELECT
        os.id AS os_id,
        DATE_FORMAT(os.created_at, '%%Y-%%m') AS periodo,
        'servico' AS categoria,
        LOWER(ser.nome) AS item,
        COUNT(*) AS quantidade_vendida,
        SUM(oss.valor_venda_real) AS vendas
    FROM os
    INNER JOIN os_servicos oss
        ON oss.os_id = os.id
    LEFT JOIN servicos ser
        ON ser.id = oss.servico_id
    INNER JOIN os_tipos ost
        ON ost.id = os.os_tipo_id
    WHERE
        os.deleted_at IS NULL
        AND oss.deleted_at IS NULL
        AND os.cancelada = 0
        AND oss.cancelado = 0
        AND ost.ativo = 1
        AND os.created_at >= %s
        AND os.created_at < DATE_ADD(%s, INTERVAL 1 DAY)
    GROUP BY
        os.id,
        periodo,
        item

    UNION ALL

    SELECT
        os.id AS os_id,
        DATE_FORMAT(os.created_at, '%%Y-%%m') AS periodo,
        'produto' AS categoria,
        LOWER(pr.nome) AS item,
        COUNT(*) AS quantidade_vendida,
        SUM(op.valor_venda_real) AS vendas
    FROM os
    INNER JOIN os_produtos op
        ON op.os_id = os.id
    LEFT JOIN produtos pr
        ON pr.id = op.produto_id
    INNER JOIN os_tipos ost
        ON ost.id = os.os_tipo_id
    WHERE
        os.deleted_at IS NULL
        AND op.deleted_at IS NULL
        AND os.cancelada = 0
        AND op.cancelado = 0
        AND ost.ativo = 1
        AND os.created_at >= %s
        AND os.created_at < DATE_ADD(%s, INTERVAL 1 DAY)
    GROUP BY
        os.id,
        periodo,
        item
) itens
GROUP BY
    periodo,
    categoria,
    item
ORDER BY
    periodo DESC,
    vendas DESC"""

ANSWERS = (
    "itens vendidos",
    "produtos vendidos",
    "serviços vendidos",
    "servicos vendidos",
    "ranking de itens",
    "ranking de produtos",
    "ranking de serviços",
    "quais itens mais venderam",
    "quais itens mais faturaram",
    "faturamento por item",
    "receita por item",
    "quantidade vendida por item",
    "ticket médio por item",
    "participação de itens no faturamento",
    "curva ABC de itens",
    "produto versus serviço",
    "produtos versus serviços",
    "revenue",
    "sales",
    "ticket",
)

VALUE_KEY = "vendas"
TIME_KEY = "periodo"
GRAIN = "month"
LABEL_KEY = "item"
DEFAULT_MEASURE = "vendas"
DEFAULT_DIMENSION = "item"
MEASURES = {
    "quantidade_vendida": {
        "label": "quantidade vendida",
        "kind": "count",
        "synonyms": (
            "quantidade",
            "volume",
            "unidades",
            "quantidade vendida",
            "mais vendidos",
        ),
        "additive": True,
    },
    "quantidade_os": {
        "label": "quantidade de OS",
        "kind": "count",
        "synonyms": ("quantidade de OS", "OS distintas", "ordens de serviço"),
        "additive": True,
    },
    "vendas": {
        "label": "vendas",
        "kind": "money",
        "synonyms": ("vendas", "faturamento", "receita", "valor vendido", "faturaram"),
        "additive": True,
    },
    "ticket_medio_item": {
        "label": "ticket médio por item",
        "kind": "money",
        "synonyms": ("ticket", "ticket médio", "ticket médio por item", "média por item"),
        "additive": False,
    },
    "ticket_medio_os": {
        "label": "ticket médio por OS",
        "kind": "money",
        "synonyms": ("ticket médio OS", "ticket médio por OS", "média por OS"),
        "additive": False,
    },
    "percentual_faturamento": {
        "label": "percentual do faturamento",
        "kind": "percent",
        "synonyms": (
            "percentual",
            "participação",
            "participação no faturamento",
            "share",
            "curva ABC",
        ),
        "additive": False,
    },
}
DIMENSIONS = {
    "periodo": {
        "label": "período",
        "synonyms": ("período", "periodo", "mês", "mes", "competência", "competencia"),
    },
    "categoria": {
        "label": "categoria",
        "synonyms": ("categoria", "tipo", "produto", "produtos", "serviço", "servico", "serviços", "servicos"),
    },
    "item": {
        "label": "item",
        "synonyms": ("item", "itens", "produto", "produtos", "serviço", "servico", "serviços", "servicos"),
    },
}
SUPPORTED_OPERATIONS = ("ranking_desc", "ranking_asc", "top_and_bottom", "list")

# 4 placeholders: serviços(date_from, date_to) + produtos(date_from, date_to)
PARAMETERS = ("date_from", "date_to", "date_from", "date_to")
