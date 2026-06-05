"""
fechamento_parcelamento_cartao
==============================

Distribuicao mensal de pagamentos no cartao por quantidade de parcelas.
"""

SQL = """\
SELECT
    DATE_FORMAT(cx.data_pagamento, '%%Y-%%m') AS periodo,
    CONCAT(cx.quant_parcelas, 'X') AS parcelas,
    cx.quant_parcelas AS quant_parcelas,
    COUNT(DISTINCT os.id) AS quantidade,
    ROUND(SUM(
        cx.valor - IFNULL((
            SELECT SUM(valor)
            FROM estornos
            WHERE caixa_id = cx.id
              AND status IN (3, 4)
              AND deleted_at IS NULL
        ), 0)
    ), 2) AS total
FROM os
JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
JOIN caixas AS cx ON cx.os_id = os.id
WHERE os.os_tipo_id IN (1, 2, 3, 4, 5, 11)
  AND os.deleted_at IS NULL
  AND cx.deleted_at IS NULL
  AND os.cancelada = 0
  AND os.paga = 1
  AND cx.caixa_tipo_id = %s
  AND os.data_pagamento >= %s
  AND os.data_pagamento < DATE_ADD(%s, INTERVAL 1 DAY)
  AND (%s = 0 OR cx.empresa_faturamento_id = %s)
  AND (%s = 0 OR conc.business_unit_id = %s)
GROUP BY cx.quant_parcelas, DATE_FORMAT(cx.data_pagamento, '%%Y-%%m')
ORDER BY cx.quant_parcelas"""

ANSWERS = (
    "parcelamento cartao",
    "parcelas do cartao",
    "pagamentos por quantidade de parcelas",
    "fechamento gerencial parcelamento no cartao",
)

VALUE_KEY = "total"
TIME_KEY = "periodo"
GRAIN = "month"
LABEL_KEY = "parcelas"
DEFAULT_MEASURE = "total"
DEFAULT_DIMENSION = "parcelas"
MEASURES = {
    "quantidade": {
        "label": "quantidade de OS",
        "kind": "count",
        "synonyms": ("quantidade", "volume", "quantidade de OS"),
        "additive": True,
    },
    "total": {
        "label": "total",
        "kind": "money",
        "synonyms": ("total", "valor", "faturamento", "receita"),
        "additive": True,
    },
}
DIMENSIONS = {
    "periodo": {
        "label": "periodo",
        "synonyms": ("periodo", "mes", "competencia"),
    },
    "parcelas": {"label": "parcelas", "synonyms": ("parcelas", "parcelamento", "vezes")},
    "quant_parcelas": {"label": "quantidade de parcelas", "synonyms": ("quantidade parcelas", "quant_parcelas")},
}
SUPPORTED_OPERATIONS = ("ranking_desc", "ranking_asc", "top_and_bottom", "list")
DEFAULT_PARAMS = {"caixa_tipo_id": 3, "empresa_faturamento_id": 0, "business_unit_id": 0}
PARAMETERS = (
    "caixa_tipo_id",
    "date_from",
    "date_to",
    "empresa_faturamento_id",
    "empresa_faturamento_id",
    "business_unit_id",
    "business_unit_id",
)
