"""
fechamento_faturamento_tipo_venda
=================================

Faturamento mensal de servicos por tipo de venda/OS.
"""

SQL = """\
SELECT
    ost.id,
    ost.nome AS os_tipo,
    ROUND(SUM(oss.valor_venda_real), 2) AS total
FROM os
JOIN os_servicos AS oss ON oss.os_id = os.id
JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
JOIN os_tipos AS ost ON os.os_tipo_id = ost.id
JOIN servicos AS serv ON oss.servico_id = serv.id
WHERE os.os_tipo_id IN (1, 2, 3, 4, 5)
  AND os.deleted_at IS NULL
  AND oss.deleted_at IS NULL
  AND ost.deleted_at IS NULL
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
GROUP BY ost.id
ORDER BY ost.id"""

ANSWERS = (
    "faturamento por tipo de venda",
    "faturamento por tipo de os",
    "vendas por tipo de servico",
    "fechamento gerencial tipo de venda servicos",
)

VALUE_KEY = "total"
TIME_KEY = None
GRAIN = "month"
LABEL_KEY = "os_tipo"
DEFAULT_MEASURE = "total"
DEFAULT_DIMENSION = "os_tipo"
MEASURES = {
    "total": {
        "label": "total",
        "kind": "money",
        "synonyms": ("total", "faturamento", "receita", "vendas"),
        "additive": True,
    },
}
DIMENSIONS = {
    "os_tipo": {"label": "tipo de venda", "synonyms": ("tipo de venda", "tipo de os", "os_tipo")},
    "id": {"label": "id do tipo de venda", "synonyms": ("id", "os_tipo_id")},
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
