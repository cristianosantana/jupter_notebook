"""
faturamento_diario
==================

Responde:
    - Quanto a empresa faturou por dia?
    - Qual a evolução diária de receita?
    - Qual o ticket médio diário?
    - Quanto foi recebido em cada forma de pagamento por dia?

Retorna:
    - data_pagamento (DATE)
    - quantidade_os (INT)
    - valor_total_recebido (DECIMAL)
    - ticket_medio (DECIMAL)
    - total_dinheiro (DECIMAL) — caixa_tipo id=1
    - total_deposito (DECIMAL) — caixa_tipo id=2
    - total_credito (DECIMAL) — caixa_tipo id=3
    - total_cheque (DECIMAL) — caixa_tipo id=4
    - total_concessionaria (DECIMAL) — caixa_tipo id=5
    - total_debito (DECIMAL) — caixa_tipo id=6
    - total_pix (DECIMAL) — caixa_tipo id=7
    - total_permuta (DECIMAL) — caixa_tipo id=8
    - total_parcelamento (DECIMAL) — caixa_tipo id=9

Parâmetros:
    - date_from (str): data início — default últimos 30 dias
    - date_to (str): data fim — default hoje

Granularidade: day
Value key: valor_total_recebido
Time key: data_pagamento
"""

SQL = """\
SELECT
    DATE(cx.data_pagamento) AS data_pagamento,
    COUNT(DISTINCT os.id) AS quantidade_os,
    ROUND(SUM(cx.valor - IFNULL(es.total_estorno, 0)), 2) AS valor_total_recebido,
    ROUND(AVG(cx.valor - IFNULL(es.total_estorno, 0)), 2) AS ticket_medio,
    ROUND(SUM(CASE WHEN ct.id = 1 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_dinheiro,
    ROUND(SUM(CASE WHEN ct.id = 2 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_deposito,
    ROUND(SUM(CASE WHEN ct.id = 3 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_credito,
    ROUND(SUM(CASE WHEN ct.id = 4 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_cheque,
    ROUND(SUM(CASE WHEN ct.id = 5 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_concessionaria,
    ROUND(SUM(CASE WHEN ct.id = 6 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_debito,
    ROUND(SUM(CASE WHEN ct.id = 7 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_pix,
    ROUND(SUM(CASE WHEN ct.id = 8 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_permuta,
    ROUND(SUM(CASE WHEN ct.id = 9 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_parcelamento
FROM caixas cx
    INNER JOIN os os ON os.id = cx.os_id
    INNER JOIN os_tipos ost ON ost.id = os.os_tipo_id
    INNER JOIN caixa_tipos ct ON ct.id = cx.caixa_tipo_id
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
    ) es ON es.caixa_id = cx.id
WHERE
    cx.deleted_at IS NULL
    AND cx.cancelado = 0
    AND cx.valor > 0
    AND ost.ativo = 1
    AND cx.data_pagamento >= %s
    AND cx.data_pagamento < DATE_ADD(%s, INTERVAL 1 DAY)
GROUP BY DATE(cx.data_pagamento)
ORDER BY cx.data_pagamento DESC"""

ANSWERS = (
    "faturamento diário",
    "receita por dia",
    "recebimentos por data",
    "quanto foi recebido por dia",
    "evolução diária de receita",
    "total cartão e pix por dia",
    "ticket médio diário",
    "revenue",
    "daily revenue",
    "ticket",
)

VALUE_KEY = "valor_total_recebido"
TIME_KEY = "data_pagamento"
GRAIN = "day"
LABEL_KEY = None
DEFAULT_MEASURE = "valor_total_recebido"
DEFAULT_DIMENSION = "data_pagamento"
MEASURES = {
    "quantidade_os": {
        "label": "quantidade de OS",
        "kind": "count",
        "synonyms": ("volume", "quantidade", "recebimentos", "quantidade de OS", "total de OS"),
        "additive": True,
    },
    "valor_total_recebido": {
        "label": "faturamento diário",
        "kind": "money",
        "synonyms": ("faturamento", "receita", "valor recebido", "total recebido"),
        "additive": True,
    },
    "ticket_medio": {
        "label": "ticket médio diário",
        "kind": "money",
        "synonyms": ("ticket", "ticket médio"),
        "additive": False,
    },
    "total_dinheiro": {"label": "dinheiro", "kind": "money", "synonyms": ("dinheiro",), "additive": True},
    "total_deposito": {"label": "depósito", "kind": "money", "synonyms": ("depósito", "deposito"), "additive": True},
    "total_credito": {"label": "crédito", "kind": "money", "synonyms": ("crédito", "credito", "cartão de crédito"), "additive": True},
    "total_cheque": {"label": "cheque", "kind": "money", "synonyms": ("cheque",), "additive": True},
    "total_concessionaria": {"label": "concessionária", "kind": "money", "synonyms": ("concessionária", "concessionaria"), "additive": True},
    "total_debito": {"label": "débito", "kind": "money", "synonyms": ("débito", "debito", "cartão de débito"), "additive": True},
    "total_pix": {"label": "pix", "kind": "money", "synonyms": ("pix",), "additive": True},
    "total_permuta": {"label": "permuta", "kind": "money", "synonyms": ("permuta",), "additive": True},
    "total_parcelamento": {"label": "parcelamento", "kind": "money", "synonyms": ("parcelamento",), "additive": True},
}
DIMENSIONS = {
    "data_pagamento": {
        "label": "data",
        "synonyms": ("data", "dia", "diário", "diario", "data pagamento", "data de pagamento"),
    },
}
SUPPORTED_OPERATIONS = ("ranking_desc", "ranking_asc", "top_and_bottom", "list")

# 4 placeholders: estornos(date_from, date_to) + pagamentos(date_from, date_to)
PARAMETERS = ("date_from", "date_to", "date_from", "date_to")
