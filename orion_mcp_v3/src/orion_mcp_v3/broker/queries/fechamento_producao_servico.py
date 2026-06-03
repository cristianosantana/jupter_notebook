"""
fechamento_producao_servico
===========================

Producao mensal por servico no fechamento gerencial.
"""

SQL = """\
SELECT
    serv.id AS servico_id,
    serv.nome AS servico,
    COUNT(DISTINCT oss.id) AS quantidade,
    ROUND(SUM(oss.valor_venda_real), 2) AS total,
    serv.custo_fixo AS custo
FROM os
JOIN os_servicos AS oss ON oss.os_id = os.id
JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
JOIN servicos AS serv ON oss.servico_id = serv.id
WHERE os.os_tipo_id IN (1, 2, 3, 4, 5)
  AND os.deleted_at IS NULL
  AND oss.deleted_at IS NULL
  AND os.cancelada = 0
  AND oss.cancelado = 0
  AND os.paga = 1
  AND os.data_pagamento >= %s
  AND os.data_pagamento < DATE_ADD(%s, INTERVAL 1 DAY)
  AND (%s = 0 OR conc.business_unit_id = %s)
  AND (
      %s = 0
      OR (%s = 1 AND serv.grupo_servico_id != 3)
      OR (%s = 2 AND serv.grupo_servico_id = 3)
  )
GROUP BY serv.id
ORDER BY serv.nome"""

ANSWERS = (
    "producao por servico",
    "servicos produzidos",
    "quantidade por servico",
    "faturamento por servico",
    "fechamento gerencial producao por servico",
)

VALUE_KEY = "total"
TIME_KEY = None
GRAIN = "month"
LABEL_KEY = "servico"
DEFAULT_MEASURE = "total"
DEFAULT_DIMENSION = "servico"
MEASURES = {
    "quantidade": {
        "label": "quantidade",
        "kind": "count",
        "synonyms": ("quantidade", "volume", "qtd", "produzido"),
        "additive": True,
    },
    "total": {
        "label": "total",
        "kind": "money",
        "synonyms": ("total", "faturamento", "receita", "valor vendido"),
        "additive": True,
    },
    "custo": {
        "label": "custo fixo",
        "kind": "money",
        "synonyms": ("custo", "custo fixo"),
        "additive": False,
    },
}
DIMENSIONS = {
    "servico": {"label": "servico", "synonyms": ("servico", "servicos", "item")},
    "servico_id": {"label": "id do servico", "synonyms": ("servico_id", "id servico")},
}
SUPPORTED_OPERATIONS = ("ranking_desc", "ranking_asc", "top_and_bottom", "list")
DEFAULT_PARAMS = {"business_unit_id": 0, "tipo_grupo_servico": 0}
PARAMETERS = (
    "date_from",
    "date_to",
    "business_unit_id",
    "business_unit_id",
    "tipo_grupo_servico",
    "tipo_grupo_servico",
    "tipo_grupo_servico",
)
