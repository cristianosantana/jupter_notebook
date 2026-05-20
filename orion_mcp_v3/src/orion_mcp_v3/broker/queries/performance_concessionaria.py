"""
performance_concessionaria
===========================

Responde:
    - Quanto cada concessionária faturou no período?
    - Qual concessionária tem maior volume de OS?
    - Qual o ranking de concessionárias por faturamento?
    - Qual o ticket médio por concessionárias?

Retorna:
    - concessionaria (VARCHAR)
    - total_os (INT)
    - total_recebimentos (INT)
    - faturamento (DECIMAL)
    - ticket_medio (DECIMAL)

Parâmetros:
    - date_from (str): data início — default últimos 30 dias
    - date_to (str): data fim — default hoje

Granularidade: total (agregado no período)
Value key: faturamento
Time key: None
Label key: concessionaria
"""

SQL = """\
SELECT
    LOWER(co.nome) AS concessionaria,
    COUNT(DISTINCT cx.os_id) AS total_os,
    COUNT(*) AS total_recebimentos,
    ROUND(SUM(cx.valor), 2) AS faturamento,
    ROUND(AVG(cx.valor), 2) AS ticket_medio
FROM caixas cx
    INNER JOIN os os ON os.id = cx.os_id
    INNER JOIN concessionarias co ON co.id = os.concessionaria_id
    INNER JOIN os_tipos ost ON ost.id = os.os_tipo_id
WHERE
    cx.deleted_at IS NULL
    AND ost.ativo = 1
    AND cx.data_vencimento >= %s AND cx.data_vencimento < %s
GROUP BY co.nome
ORDER BY faturamento DESC"""

ANSWERS = (
    "faturamento por concessionária",
    "performance de concessionária",
    "receita por concessionária",
    "ranking de concessionárias",
    "comparação entre concessionárias",
    "qual concessionária fatura mais",
    "revenue",
    "sales",
)

VALUE_KEY = "faturamento"
TIME_KEY = None
GRAIN = "total"
LABEL_KEY = "concessionaria"
DEFAULT_MEASURE = "faturamento"
DEFAULT_DIMENSION = "concessionaria"
MEASURES = {
    "total_os": {
        "label": "volume de OS",
        "kind": "count",
        "synonyms": ("volume", "volume de vendas", "total de OS", "quantidade de OS"),
        "additive": True,
    },
    "total_recebimentos": {
        "label": "volume de recebimentos",
        "kind": "count",
        "synonyms": ("recebimentos", "total de recebimentos"),
        "additive": True,
    },
    "faturamento": {
        "label": "receita/faturamento",
        "kind": "money",
        "synonyms": ("faturamento", "receita", "valor de vendas"),
        "additive": True,
    },
    "ticket_medio": {
        "label": "ticket médio",
        "kind": "money",
        "synonyms": ("ticket", "ticket médio"),
        "additive": False,
    },
}
DIMENSIONS = {
    "concessionaria": {
        "label": "concessionária",
        "synonyms": ("concessionária", "concessionaria", "loja", "unidade"),
    },
}
SUPPORTED_OPERATIONS = ("ranking_desc", "ranking_asc", "top_and_bottom", "list")
