"""
fechamento_faturamento_tipo_venda_produtos
==========================================

Faturamento mensal de produtos para OS do tipo 11.
"""

SQL = """\
SELECT
    ost.id,
    ost.nome AS tipo_venda_material,
    ROUND(SUM(osp.valor_venda_real), 2) AS total
FROM os
JOIN os_produtos AS osp ON osp.os_id = os.id
JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
JOIN os_tipos AS ost ON os.os_tipo_id = ost.id
WHERE os.os_tipo_id = 11
  AND os.deleted_at IS NULL
  AND osp.deleted_at IS NULL
  AND ost.deleted_at IS NULL
  AND os.cancelada = 0
  AND osp.cancelado = 0
  AND os.paga = 1
  AND os.data_pagamento >= %s
  AND os.data_pagamento < DATE_ADD(%s, INTERVAL 1 DAY)
  AND (%s = 0 OR conc.business_unit_id = %s)
GROUP BY ost.id
ORDER BY ost.id"""

ANSWERS = (
    "faturamento de venda de materias",
    "faturamento de venda de materias",
    "vendas de materias",
    "fechamento gerencial venda de materias",
)

VALUE_KEY = "total"
TIME_KEY = None
GRAIN = "month"
LABEL_KEY = "venda_material"
DEFAULT_MEASURE = "total"
DEFAULT_DIMENSION = "venda_material"
MEASURES = {
    "total": {
        "label": "total",
        "kind": "money",
        "synonyms": ("total", "faturamento", "receita", "vendas", "produtos"),
        "additive": True,
    },
}
DIMENSIONS = {
    "venda_material": {
        "label": "venda de material",
        "synonyms": ("venda de material", "venda de materiais"),
        "sortable": True,
    },
    "id": {
        "label": "id do tipo de venda de material",
        "synonyms": ("id", "os_tipo_id", "id tipo venda material"),
        "sortable": True,
    },
}
SUPPORTED_OPERATIONS = ("ranking_desc", "ranking_asc", "top_and_bottom", "list")
DEFAULT_PARAMS = {"business_unit_id": 0}
PARAMETERS = ("date_from", "date_to", "business_unit_id", "business_unit_id")
