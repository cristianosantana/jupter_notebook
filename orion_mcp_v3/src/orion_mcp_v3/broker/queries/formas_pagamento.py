"""
formas_pagamento
=================

Responde:
    - Qual a distribuição de receita por forma de pagamento?
    - Quanto foi recebido em PIX, cartão, dinheiro etc.?
    - Qual o percentual de cada forma de pagamento sobre o total vendido?
    - Qual forma de pagamento é mais utilizada?

Retorna:
    - forma_pagamento (VARCHAR)
    - qtd_recebimentos (INT)
    - total_recebido (DECIMAL)
    - ticket_medio (DECIMAL)
    - percentual_total (DECIMAL) — % sobre total geral

Parâmetros:
    - date_from (str): data início — default últimos 30 dias
    - date_to (str): data fim — default hoje

Granularidade: total (agregado no período)
Value key: total_recebido
Time key: None
Label key: forma_pagamento
"""

SQL = """\
SELECT
    LOWER(ct.nome) AS forma_pagamento,
    COUNT(*) AS qtd_recebimentos,
    ROUND(SUM(cx.valor), 2) AS total_recebido,
    ROUND(AVG(cx.valor), 2) AS ticket_medio,
    ROUND(
        (SUM(cx.valor) / (
            SELECT SUM(c2.valor)
            FROM caixas c2
                INNER JOIN os o2 ON o2.id = c2.os_id
                INNER JOIN os_tipos ost2 ON ost2.id = o2.os_tipo_id
            WHERE c2.deleted_at IS NULL
                AND ost2.ativo = 1
                AND c2.data_vencimento >= %s AND c2.data_vencimento < %s
        )) * 100, 2
    ) AS percentual_total
FROM caixas cx
    INNER JOIN caixa_tipos ct ON ct.id = cx.caixa_tipo_id
    INNER JOIN os os ON os.id = cx.os_id
    INNER JOIN os_tipos ost ON ost.id = os.os_tipo_id
WHERE
    cx.deleted_at IS NULL
    AND ost.ativo = 1
    AND cx.data_vencimento >= %s AND cx.data_vencimento < %s
GROUP BY ct.nome
ORDER BY total_recebido DESC"""

ANSWERS = (
    "formas de pagamento",
    "forma de pagamento",
    "distribuição por forma de pagamento",
    "percentual por forma de pagamento",
    "quanto foi pago em pix",
    "quanto foi pago em cartão",
    "receita por tipo de pagamento",
    "revenue",
    "sales",
)

VALUE_KEY = "total_recebido"
TIME_KEY = None
GRAIN = "total"
LABEL_KEY = "forma_pagamento"
DEFAULT_MEASURE = "total_recebido"
DEFAULT_DIMENSION = "forma_pagamento"
MEASURES = {
    "qtd_recebimentos": {
        "label": "quantidade de recebimentos",
        "kind": "count",
        "synonyms": ("quantidade", "volume", "qtd recebimentos"),
        "additive": True,
    },
    "total_recebido": {
        "label": "total recebido",
        "kind": "money",
        "synonyms": ("recebido", "faturamento", "receita", "total recebido"),
        "additive": True,
    },
    "ticket_medio": {
        "label": "ticket médio",
        "kind": "money",
        "synonyms": ("ticket", "ticket médio"),
        "additive": False,
    },
    "percentual_total": {
        "label": "percentual sobre o total",
        "kind": "percent",
        "synonyms": ("percentual", "participação", "share"),
        "additive": False,
    },
}
DIMENSIONS = {
    "forma_pagamento": {
        "label": "forma de pagamento",
        "synonyms": ("forma de pagamento", "pagamento", "meio de pagamento"),
    },
}
SUPPORTED_OPERATIONS = ("ranking_desc", "ranking_asc", "top_and_bottom", "list")

# 4 placeholders: subquery(date_from, date_to) + WHERE(date_from, date_to)
PARAMETERS = ("date_from", "date_to", "date_from", "date_to")
