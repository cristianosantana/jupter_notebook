"""
fechamento_comissao_concessionaria_servicos
===========================================

Comissao por concessionaria no fechamento gerencial mensal, considerando
servicos de OS dos tipos 1, 2 e 11.
"""

SQL = """\
SELECT
    conc.nome AS concessionaria,
    ROUND(SUM(IF(com.estorno IS NULL OR com.estorno != 1, oss.valor_venda_real, oss.valor_venda_real * -1)), 2) AS total,
    ROUND(SUM(IF(com.estorno IS NULL OR com.estorno != 1, com.valor_dentro + com.valor_fora, (com.valor_dentro + com.valor_fora) * -1)), 2) AS total_comissao
FROM os
JOIN os_servicos AS oss ON oss.os_id = os.id
JOIN servicos AS serv ON serv.id = oss.servico_id
JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
LEFT JOIN comissoes AS com
    ON com.comissionado_id = conc.id
    AND com.comissao_tipo_id = 1
    AND com.os_servico_id = oss.id
WHERE os.os_tipo_id IN (1, 2, 11)
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
ORDER BY concessionaria"""

ANSWERS = (
    "comissao por concessionaria servicos",
    "comissoes de concessionarias servicos",
    "fechamento gerencial comissao por concessionaria",
    "total de comissao por concessionaria",
    "concessionaria com maior comissao",
)

VALUE_KEY = "total_comissao"
TIME_KEY = None
GRAIN = "month"
LABEL_KEY = "concessionaria"
DEFAULT_MEASURE = "total_comissao"
DEFAULT_DIMENSION = "concessionaria"
MEASURES = {
    "total": {
        "label": "total vendido",
        "kind": "money",
        "synonyms": ("total", "vendas", "faturamento", "valor vendido"),
        "additive": True,
    },
    "total_comissao": {
        "label": "total de comissao",
        "kind": "money",
        "synonyms": ("comissao", "comissao total", "total comissao", "comissoes"),
        "additive": True,
    },
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
