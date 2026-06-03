"""
fechamento_comissao_concessionaria_tipos
========================================

Composicao de valores por concessionaria em corte, financeiro e prestacao.
"""

SQL = """\
SELECT
    conc.nome AS concessionaria,
    ROUND(SUM(IF(os.os_tipo_id IN (2, 3), IF(com.estorno IS NULL OR com.estorno != 1, oss.valor_venda_real, oss.valor_venda_real * -1), 0)), 2) AS total,
    ROUND(SUM(IF(os.os_tipo_id = 3, IF(com.estorno IS NULL OR com.estorno != 1, oss.valor_venda_real, oss.valor_venda_real * -1), 0)), 2) AS total_cort,
    ROUND(SUM(IF(os.os_tipo_id = 2, IF(com.estorno IS NULL OR com.estorno != 1, oss.valor_venda_real, oss.valor_venda_real * -1), 0)), 2) AS total_fin,
    ROUND(SUM(IF(os.os_tipo_id = 5, IF(com.estorno IS NULL OR com.estorno != 1, oss.valor_venda_real, oss.valor_venda_real * -1), 0)), 2) AS total_prest
FROM os
JOIN os_servicos AS oss ON oss.os_id = os.id
JOIN servicos AS serv ON serv.id = oss.servico_id
JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
LEFT JOIN comissoes AS com
    ON com.comissionado_id = conc.id
    AND com.comissao_tipo_id = 1
    AND com.os_servico_id = oss.id
WHERE os.os_tipo_id IN (2, 3, 5)
  AND os.deleted_at IS NULL
  AND oss.deleted_at IS NULL
  AND com.deleted_at IS NULL
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
GROUP BY os.concessionaria_id
ORDER BY conc.nome"""

ANSWERS = (
    "composicao de comissao por concessionaria",
    "comissao concessionaria por tipo",
    "corte financeiro prestacao por concessionaria",
    "fechamento gerencial concessionaria por tipo de venda",
)

VALUE_KEY = "total"
TIME_KEY = None
GRAIN = "month"
LABEL_KEY = "concessionaria"
DEFAULT_MEASURE = "total"
DEFAULT_DIMENSION = "concessionaria"
MEASURES = {
    "total": {"label": "total", "kind": "money", "synonyms": ("total", "vendas"), "additive": True},
    "total_cort": {"label": "total corte", "kind": "money", "synonyms": ("corte", "cortesia"), "additive": True},
    "total_fin": {"label": "total financeiro", "kind": "money", "synonyms": ("financeiro", "financiamento"), "additive": True},
    "total_prest": {"label": "total prestacao", "kind": "money", "synonyms": ("prestacao", "prestacao de servico"), "additive": True},
}
DIMENSIONS = {
    "concessionaria": {
        "label": "concessionaria",
        "synonyms": ("concessionaria", "concessionarias", "loja", "lojas"),
    },
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
