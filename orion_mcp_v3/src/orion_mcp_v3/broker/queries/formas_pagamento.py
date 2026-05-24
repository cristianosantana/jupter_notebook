"""
formas_pagamento
=================

Responde:
    - Qual a distribuição mensal de receita por forma de pagamento?
    - Quanto foi recebido em PIX, cartão, dinheiro etc.?
    - Qual o percentual de cada forma de pagamento sobre o total recebido?
    - Qual o ticket médio por OS paga?

Retorna:
    - periodo (VARCHAR, YYYY-MM)
    - quantidade_os (INT)
    - total (DECIMAL)
    - ticket_medio_os (DECIMAL)
    - dinheiro (DECIMAL)
    - deposito (DECIMAL)
    - cartao_credito (DECIMAL)
    - cortesia (DECIMAL)
    - pix (DECIMAL)
    - percentual_dinheiro (DECIMAL)
    - percentual_deposito (DECIMAL)
    - percentual_credito (DECIMAL)
    - percentual_cortesia (DECIMAL)
    - percentual_pix (DECIMAL)

Parâmetros:
    - date_from (str): data início — default últimos 30 dias
    - date_to (str): data fim — default hoje

Granularidade: month (agregado por período)
Value key: total
Time key: periodo
Label key: periodo
"""

SQL = """\
SELECT
    DATE_FORMAT(os.data_pagamento, '%%Y-%%m') AS periodo,
    COUNT(DISTINCT os.id) AS quantidade_os,
    ROUND(SUM(financeiro.recebido_total), 2) AS total,
    ROUND(SUM(financeiro.recebido_total) / COUNT(DISTINCT os.id), 2) AS ticket_medio_os,
    ROUND(SUM(financeiro.recebido_dinheiro), 2) AS dinheiro,
    ROUND(SUM(financeiro.recebido_deposito), 2) AS deposito,
    ROUND(SUM(financeiro.recebido_credito), 2) AS cartao_credito,
    ROUND(SUM(financeiro.recebido_concessionaria), 2) AS cortesia,
    ROUND(SUM(financeiro.recebido_pix), 2) AS pix,
    ROUND((SUM(financeiro.recebido_dinheiro) / SUM(financeiro.recebido_total)) * 100, 2) AS percentual_dinheiro,
    ROUND((SUM(financeiro.recebido_deposito) / SUM(financeiro.recebido_total)) * 100, 2) AS percentual_deposito,
    ROUND((SUM(financeiro.recebido_credito) / SUM(financeiro.recebido_total)) * 100, 2) AS percentual_credito,
    ROUND((SUM(financeiro.recebido_concessionaria) / SUM(financeiro.recebido_total)) * 100, 2) AS percentual_cortesia,
    ROUND((SUM(financeiro.recebido_pix) / SUM(financeiro.recebido_total)) * 100, 2) AS percentual_pix
FROM os
INNER JOIN os_tipos ost
    ON ost.id = os.os_tipo_id
INNER JOIN (
    SELECT
        cx.os_id,
        SUM(cx.valor - IFNULL(es.total_estorno, 0)) AS recebido_total,
        SUM(
            CASE
                WHEN ct.id = 1
                THEN cx.valor - IFNULL(es.total_estorno, 0)
                ELSE 0
            END
        ) AS recebido_dinheiro,
        SUM(
            CASE
                WHEN ct.id = 2
                THEN cx.valor - IFNULL(es.total_estorno, 0)
                ELSE 0
            END
        ) AS recebido_deposito,
        SUM(
            CASE
                WHEN ct.id = 3
                THEN cx.valor - IFNULL(es.total_estorno, 0)
                ELSE 0
            END
        ) AS recebido_credito,
        SUM(
            CASE
                WHEN ct.id = 5
                THEN cx.valor - IFNULL(es.total_estorno, 0)
                ELSE 0
            END
        ) AS recebido_concessionaria,
        SUM(
            CASE
                WHEN ct.id = 7
                THEN cx.valor - IFNULL(es.total_estorno, 0)
                ELSE 0
            END
        ) AS recebido_pix
    FROM caixas cx
    INNER JOIN caixa_tipos ct
        ON ct.id = cx.caixa_tipo_id
    LEFT JOIN (
        SELECT
            caixa_id,
            SUM(valor) AS total_estorno
        FROM estornos
        WHERE
            status IN (3, 4)
            AND deleted_at IS NULL
            AND created_at >= %s
            AND created_at < DATE_ADD(%s, INTERVAL 1 DAY)
        GROUP BY caixa_id
    ) es
        ON es.caixa_id = cx.id
    WHERE
        cx.deleted_at IS NULL
        AND cx.cancelado = 0
        AND cx.valor > 0
    GROUP BY cx.os_id
) financeiro
    ON financeiro.os_id = os.id
WHERE
    os.deleted_at IS NULL
    AND os.paga = 1
    AND ost.ativo = 1
    AND os.data_pagamento >= %s
    AND os.data_pagamento < DATE_ADD(%s, INTERVAL 1 DAY)
GROUP BY
    DATE_FORMAT(os.data_pagamento, '%%Y-%%m')
ORDER BY periodo DESC"""

ANSWERS = (
    "formas de pagamento",
    "forma de pagamento",
    "mix financeiro",
    "distribuição mensal por forma de pagamento",
    "distribuição por forma de pagamento",
    "percentual por forma de pagamento",
    "percentual de pix",
    "percentual de cartão",
    "percentual de dinheiro",
    "quanto foi pago em pix",
    "quanto foi pago em cartão",
    "receita por tipo de pagamento",
    "ticket médio por OS",
    "revenue",
    "sales",
)

VALUE_KEY = "total"
TIME_KEY = "periodo"
GRAIN = "month"
LABEL_KEY = "periodo"
DEFAULT_MEASURE = "total"
DEFAULT_DIMENSION = "periodo"
MEASURES = {
    "quantidade_os": {
        "label": "quantidade de OS",
        "kind": "count",
        "synonyms": ("quantidade", "volume", "quantidade de OS", "total de OS"),
        "additive": True,
    },
    "total": {
        "label": "total recebido",
        "kind": "money",
        "synonyms": ("total", "recebido", "faturamento", "receita", "total recebido"),
        "additive": True,
    },
    "ticket_medio_os": {
        "label": "ticket médio por OS",
        "kind": "money",
        "synonyms": ("ticket", "ticket médio", "ticket médio OS", "média por OS"),
        "additive": False,
    },
    "dinheiro": {
        "label": "dinheiro",
        "kind": "money",
        "synonyms": ("dinheiro", "recebido dinheiro", "pagamento em dinheiro"),
        "additive": True,
    },
    "deposito": {
        "label": "depósito",
        "kind": "money",
        "synonyms": ("depósito", "deposito", "recebido depósito", "recebido deposito"),
        "additive": True,
    },
    "cartao_credito": {
        "label": "cartão de crédito",
        "kind": "money",
        "synonyms": ("cartão", "cartao", "cartão crédito", "cartao credito", "crédito", "credito"),
        "additive": True,
    },
    "cortesia": {
        "label": "cortesia/concessionária",
        "kind": "money",
        "synonyms": ("cortesia", "concessionária", "concessionaria"),
        "additive": True,
    },
    "pix": {
        "label": "pix",
        "kind": "money",
        "synonyms": ("pix", "recebido pix"),
        "additive": True,
    },
    "percentual_dinheiro": {
        "label": "percentual dinheiro",
        "kind": "percent",
        "synonyms": ("percentual dinheiro", "% dinheiro", "participação dinheiro"),
        "additive": False,
    },
    "percentual_deposito": {
        "label": "percentual depósito",
        "kind": "percent",
        "synonyms": ("percentual depósito", "percentual deposito", "% depósito", "% deposito"),
        "additive": False,
    },
    "percentual_credito": {
        "label": "percentual crédito",
        "kind": "percent",
        "synonyms": ("percentual crédito", "percentual credito", "% crédito", "% credito"),
        "additive": False,
    },
    "percentual_cortesia": {
        "label": "percentual cortesia",
        "kind": "percent",
        "synonyms": ("percentual cortesia", "% cortesia", "participação cortesia"),
        "additive": False,
    },
    "percentual_pix": {
        "label": "percentual pix",
        "kind": "percent",
        "synonyms": ("percentual pix", "% pix", "participação pix"),
        "additive": False,
    },
}
DIMENSIONS = {
    "periodo": {
        "label": "período",
        "synonyms": ("período", "periodo", "mês", "mes", "competência", "competencia"),
    },
}
SUPPORTED_OPERATIONS = ("ranking_desc", "ranking_asc", "top_and_bottom", "list")

# 4 placeholders: estornos(date_from, date_to) + OS pagas(date_from, date_to)
PARAMETERS = ("date_from", "date_to", "date_from", "date_to")
