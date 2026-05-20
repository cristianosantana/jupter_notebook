"""
visao_executiva
================

Responde:
    - faturamento por concessionária;
    - total de OS por concessionária;
    - ticket médio por concessionária;
    - maior recebimento por concessionária;
    - menor recebimento por concessionária;
    - ranking maior/menor por qualquer uma dessas métricas;
    - análise por período mensal.

Retorna:
    - periodo (VARCHAR) — formato YYYY-MM
    - concessionaria (VARCHAR)
    - total_os (INT)
    - faturamento (DECIMAL)
    - ticket_medio (DECIMAL)
    - maior_recebimento (DECIMAL)
    - menor_recebimento (DECIMAL)

Parâmetros:
    - date_from (str): data início — default últimos 30 dias
    - date_to (str): data fim — default hoje

Granularidade: month
Value key: faturamento
Time key: periodo
Label key: concessionaria

Ideal para:
    - Power BI / Metabase / Looker Studio
    - Dashboard executivo
    - Reunião gerencial
    - Comparativo mensal entre lojas
"""

SQL = """\
SELECT
    DATE_FORMAT(cx.data_vencimento, '%%Y-%%m') AS periodo,
    LOWER(co.nome) AS concessionaria,
    COUNT(DISTINCT os.id) AS total_os,
    ROUND(SUM(cx.valor), 2) AS faturamento,
    ROUND(AVG(cx.valor), 2) AS ticket_medio,
    ROUND(MAX(cx.valor), 2) AS maior_recebimento,
    ROUND(MIN(cx.valor), 2) AS menor_recebimento
FROM caixas cx
    INNER JOIN os os ON os.id = cx.os_id
    INNER JOIN concessionarias co ON co.id = os.concessionaria_id
    INNER JOIN os_tipos ost ON ost.id = os.os_tipo_id
WHERE
    cx.deleted_at IS NULL
    AND ost.ativo = 1
    AND cx.data_vencimento >= %s AND cx.data_vencimento < %s
GROUP BY
    DATE_FORMAT(cx.data_vencimento, '%%Y-%%m'),
    co.nome
ORDER BY periodo DESC, faturamento DESC"""

ANSWERS = (
    "visão executiva",
    "relatório completo",
    "power bi",
    "dados completos de faturamento",
    "faturamento por concessionária e mês",
    "cada concessionária faturou por mês",
    "cada concessionária faturou",
    "dashboard executivo",
    "revenue",
    "sales",
)

VALUE_KEY = "faturamento"
TIME_KEY = "periodo"
GRAIN = "month"
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
    "faturamento": {
        "label": "receita/faturamento",
        "kind": "money",
        "synonyms": ("receita", "faturamento", "valor de vendas", "valor vendido"),
        "additive": True,
    },
    "ticket_medio": {
        "label": "ticket médio",
        "kind": "money",
        "synonyms": ("ticket", "ticket médio", "média por OS"),
        "additive": False,
    },
    "maior_recebimento": {
        "label": "maior recebimento individual",
        "kind": "money",
        "synonyms": ("maior recebimento", "maior venda individual", "maior valor individual"),
        "additive": False,
    },
    "menor_recebimento": {
        "label": "menor recebimento individual",
        "kind": "money",
        "synonyms": ("menor recebimento", "menor venda individual", "menor valor individual"),
        "additive": False,
    },
}
DIMENSIONS = {
    "concessionaria": {
        "label": "concessionária",
        "synonyms": ("concessionária", "concessionaria", "loja", "unidade"),
    },
    "periodo": {
        "label": "período",
        "synonyms": ("período", "periodo", "mês", "mes"),
    },
}
SUPPORTED_OPERATIONS = ("ranking_desc", "ranking_asc", "top_and_bottom", "list")
