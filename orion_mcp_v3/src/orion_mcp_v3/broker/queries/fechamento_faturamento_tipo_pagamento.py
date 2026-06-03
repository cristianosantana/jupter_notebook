"""
fechamento_faturamento_tipo_pagamento
=====================================

Pagamentos, estornos e total liquido por forma de pagamento no fechamento mensal.
"""

SQL = """\
SELECT
    ct.id AS caixa_tipo_id,
    ct.nome AS caixa_tipo,
    COALESCE(p.total_pagamentos, 0) AS total_pagamentos,
    COALESCE(e.total_estornos, 0) AS total_estornos,
    (COALESCE(p.total_pagamentos, 0) - COALESCE(e.total_estornos, 0)) AS total_liquido
FROM caixa_tipos ct
LEFT JOIN (
    SELECT
        cx.caixa_tipo_id,
        ROUND(SUM(cx.valor), 2) AS total_pagamentos
    FROM caixas AS cx
    INNER JOIN os ON cx.os_id = os.id
    INNER JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
    WHERE os.deleted_at IS NULL
      AND cx.deleted_at IS NULL
      AND os.os_tipo_id IN (1, 2, 3, 4, 5, 11)
      AND os.cancelada = 0
      AND os.paga = 1
      AND os.data_pagamento >= %s
      AND os.data_pagamento < DATE_ADD(%s, INTERVAL 1 DAY)
      AND (%s = 0 OR conc.business_unit_id = %s)
    GROUP BY cx.caixa_tipo_id
) p ON ct.id = p.caixa_tipo_id
LEFT JOIN (
    SELECT
        cx.caixa_tipo_id,
        ROUND(SUM(est.valor), 2) AS total_estornos
    FROM estornos AS est
    INNER JOIN caixas AS cx ON est.caixa_id = cx.id
    INNER JOIN os ON cx.os_id = os.id
    INNER JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
    WHERE os.deleted_at IS NULL
      AND est.deleted_at IS NULL
      AND cx.deleted_at IS NULL
      AND est.status > 2
      AND os.os_tipo_id IN (1, 2, 3, 4, 5)
      AND os.cancelada = 0
      AND est.updated_at >= %s
      AND est.updated_at < DATE_ADD(%s, INTERVAL 1 DAY)
      AND (%s = 0 OR conc.business_unit_id = %s)
    GROUP BY cx.caixa_tipo_id
) e ON ct.id = e.caixa_tipo_id
WHERE ct.ativo = 1
ORDER BY ct.id"""

ANSWERS = (
    "faturamento por tipo de pagamento",
    "pagamentos por forma",
    "estornos por forma de pagamento",
    "total liquido por tipo de caixa",
    "fechamento gerencial tipo de pagamento",
)

VALUE_KEY = "total_liquido"
TIME_KEY = None
GRAIN = "month"
LABEL_KEY = "caixa_tipo"
DEFAULT_MEASURE = "total_liquido"
DEFAULT_DIMENSION = "caixa_tipo"
MEASURES = {
    "total_pagamentos": {
        "label": "total pagamentos",
        "kind": "money",
        "synonyms": ("pagamentos", "recebido", "total pagamentos"),
        "additive": True,
    },
    "total_estornos": {
        "label": "total estornos",
        "kind": "money",
        "synonyms": ("estornos", "devolucoes", "total estornos"),
        "additive": True,
    },
    "total_liquido": {
        "label": "total liquido",
        "kind": "money",
        "synonyms": ("liquido", "total liquido", "receita liquida", "faturamento liquido"),
        "additive": True,
    },
}
DIMENSIONS = {
    "caixa_tipo": {
        "label": "tipo de pagamento",
        "synonyms": ("tipo de pagamento", "forma de pagamento", "caixa tipo", "caixa_tipo"),
    },
    "caixa_tipo_id": {
        "label": "id do tipo de pagamento",
        "synonyms": ("caixa_tipo_id", "id tipo pagamento"),
    },
}
SUPPORTED_OPERATIONS = ("ranking_desc", "ranking_asc", "top_and_bottom", "list")
DEFAULT_PARAMS = {"business_unit_id": 0}
PARAMETERS = (
    "date_from",
    "date_to",
    "business_unit_id",
    "business_unit_id",
    "date_from",
    "date_to",
    "business_unit_id",
    "business_unit_id",
)
