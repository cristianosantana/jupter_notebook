"""
fechamento_producao_produto
===========================

Producao mensal por produto no fechamento gerencial.
"""

SQL = """\
SELECT
    prod.id AS produto_id,
    prod.nome AS produto,
    COUNT(DISTINCT osp.id) AS quantidade,
    ROUND(SUM(osp.valor_venda_real), 2) AS total
FROM os
JOIN os_produtos AS osp ON osp.os_id = os.id
JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
JOIN produtos AS prod ON osp.produto_id = prod.id
WHERE os.os_tipo_id = 11
  AND os.deleted_at IS NULL
  AND osp.deleted_at IS NULL
  AND os.cancelada = 0
  AND osp.cancelado = 0
  AND os.paga = 1
  AND os.data_pagamento >= %s
  AND os.data_pagamento < DATE_ADD(%s, INTERVAL 1 DAY)
  AND (%s = 0 OR conc.business_unit_id = %s)
GROUP BY prod.id
ORDER BY prod.nome"""

ANSWERS = (
    "producao por produto",
    "produtos produzidos",
    "quantidade por produto",
    "faturamento por produto",
    "fechamento gerencial producao por produto",
)

VALUE_KEY = "total"
TIME_KEY = None
GRAIN = "month"
LABEL_KEY = "produto"
DEFAULT_MEASURE = "total"
DEFAULT_DIMENSION = "produto"
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
}
DIMENSIONS = {
    "produto": {"label": "produto", "synonyms": ("produto", "produtos", "item")},
    "produto_id": {"label": "id do produto", "synonyms": ("produto_id", "id produto")},
}
SUPPORTED_OPERATIONS = ("ranking_desc", "ranking_asc", "top_and_bottom", "list")
DEFAULT_PARAMS = {"business_unit_id": 0}
PARAMETERS = ("date_from", "date_to", "business_unit_id", "business_unit_id")
