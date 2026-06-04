"""
fechamento_faturamento_comissao_tipo_os_concessionaria_periodo
==============================================================

Faturamento e detalhamento de comissão por tipo de O.S., concessionária e período.
"""

SQL = """\
SELECT
    DATE_FORMAT(os.data_pagamento, '%%Y-%%m') AS periodo,
    conc.nome AS concessionaria,
    ROUND(SUM(IF(com.estorno IS NULL OR com.estorno != 1, oss.valor_venda_real, oss.valor_venda_real * -1)), 2) AS total_faturamento,
    ROUND(SUM(IF(com.estorno IS NULL OR com.estorno != 1, com.valor_dentro, com.valor_dentro * -1)), 2) AS total_comissao,
    ROUND(SUM(IF(os.os_tipo_id = 1, IF(com.estorno IS NULL OR com.estorno != 1, com.valor_dentro, com.valor_dentro * -1), 0)), 2) AS comissao_venda_normal,
    ROUND(SUM(IF(os.os_tipo_id = 2, IF(com.estorno IS NULL OR com.estorno != 1, com.valor_dentro, com.valor_dentro * -1), 0)), 2) AS comissao_financiamento
FROM os
JOIN os_servicos AS oss ON oss.os_id = os.id
JOIN servicos AS serv ON serv.id = oss.servico_id
JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
JOIN comissoes AS com
    ON com.comissionado_id = conc.id
    AND com.comissao_tipo_id = 1
    AND com.os_servico_id = oss.id
WHERE os.os_tipo_id IN (1, 2)
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
GROUP BY os.concessionaria_id, conc.nome, DATE_FORMAT(os.data_pagamento, '%%Y-%%m')
ORDER BY conc.nome"""

ANSWERS = (
    "faturamento e comissao por tipo de os concessionaria e periodo",
    "detalhamento de comissao por tipo de os",
    "comissao venda normal e financiamento por concessionaria",
    "fechamento gerencial comissao por tipo de os",
)

VALUE_KEY = "total_comissao"
TIME_KEY = "periodo"
GRAIN = "month"
LABEL_KEY = "concessionaria"
DEFAULT_MEASURE = "total_comissao"
DEFAULT_DIMENSION = "concessionaria"
MEASURES = {
    "total_faturamento": {
        "label": "total faturamento",
        "kind": "money",
        "synonyms": ("faturamento", "receita", "vendas", "total faturamento"),
        "additive": True,
    },
    "total_comissao": {
        "label": "total comissao",
        "kind": "money",
        "synonyms": ("comissao", "comissao total", "total comissao", "comissoes"),
        "additive": True,
    },
    "comissao_venda_normal": {
        "label": "comissao venda normal",
        "kind": "money",
        "synonyms": ("venda normal", "comissao venda normal", "normal"),
        "additive": True,
    },
    "comissao_financiamento": {
        "label": "comissao financiamento",
        "kind": "money",
        "synonyms": ("financiamento", "comissao financiamento", "financeiro"),
        "additive": True,
    },
}
DIMENSIONS = {
    "periodo": {
        "label": "periodo",
        "synonyms": ("periodo", "mes", "competencia"),
    },
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
