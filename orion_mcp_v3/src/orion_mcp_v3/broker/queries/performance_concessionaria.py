"""
performance_concessionaria
===========================

Responde:
    - Quanto cada concessionária vendeu no período?
    - Quanto cada concessionária recebeu no período?
    - Qual concessionária tem maior volume de OS?
    - Qual o ranking de concessionárias por faturamento?
    - Qual o ticket médio por OS?
    - Qual o percentual recebido sobre vendas?

Retorna:
    - periodo (VARCHAR, MM/YYYY)
    - concessionaria (VARCHAR)
    - quantidade_os (INT)
    - vendas (DECIMAL)
    - ticket_medio_os (DECIMAL)
    - recebido (DECIMAL)
    - percentual_recebido (DECIMAL)

Parâmetros:
    - date_from (str): data início — default últimos 30 dias
    - date_to (str): data fim — default hoje

Granularidade: month (agregado por período/concessionária)
Value key: vendas
Time key: periodo
Label key: concessionaria
"""

SQL = """\
SELECT
    DATE_FORMAT(os.created_at, '%m/%Y') AS periodo,
    LOWER(co.nome) AS concessionaria,
    COUNT(DISTINCT os.id) AS quantidade_os,
    ROUND(SUM(COALESCE(os_vendas.valor_venda, 0)), 2) AS vendas,
    ROUND(SUM(COALESCE(os_vendas.valor_venda, 0)) / COUNT(DISTINCT os.id), 2) AS ticket_medio_os,
    ROUND(SUM(COALESCE(cx_recebido.valor_recebido, 0)), 2) AS recebido,
    ROUND(
        (
            SUM(COALESCE(cx_recebido.valor_recebido, 0))
            / IF(
                SUM(COALESCE(os_vendas.valor_venda, 0)) = 0,
                1,
                SUM(COALESCE(os_vendas.valor_venda, 0))
            )
        ) * 100,
        2
    ) AS percentual_recebido
FROM os os
LEFT JOIN (
    SELECT
        oss.os_id,
        SUM(oss.valor_venda_real) AS valor_venda
    FROM os_servicos oss
    WHERE
        oss.deleted_at IS NULL
        AND oss.cancelado = 0
    GROUP BY oss.os_id
) os_vendas
    ON os_vendas.os_id = os.id
INNER JOIN concessionarias co
    ON co.id = os.concessionaria_id
LEFT JOIN (
    SELECT
        cx.os_id,
        SUM(cx.valor - IFNULL(es.total_estorno, 0)) AS valor_recebido
    FROM caixas cx
    LEFT JOIN (
        SELECT
            caixa_id,
            SUM(valor) AS total_estorno
        FROM estornos
        WHERE
            status IN (3, 4)
            AND deleted_at IS NULL
            AND created_at >= %s
            AND created_at < DATE_ADD(%s, INTERVAL 1 DAY)
        GROUP BY caixa_id
    ) es ON es.caixa_id = cx.id
    WHERE
        cx.deleted_at IS NULL
        AND cx.cancelado = 0
        AND cx.valor > 0
        AND cx.data_pagamento >= %s
        AND cx.data_pagamento < DATE_ADD(%s, INTERVAL 1 DAY)
    GROUP BY cx.os_id
) cx_recebido
    ON cx_recebido.os_id = os.id
WHERE
    os.deleted_at IS NULL
    AND co.deleted_at IS NULL
    AND os.cancelada = 0
    AND os.os_tipo_id IN (1, 2, 5)
    AND os.created_at >= %s
    AND os.created_at < DATE_ADD(%s, INTERVAL 1 DAY)
GROUP BY DATE_FORMAT(os.created_at, '%m/%Y'), co.id, co.nome
ORDER BY periodo DESC, vendas DESC"""

ANSWERS = (
    "vendas por concessionária",
    "performance de concessionária",
    "faturamento por concessionária",
    "receita por concessionária",
    "recebido por concessionária",
    "percentual recebido por concessionária",
    "ranking de concessionárias",
    "comparação entre concessionárias",
    "qual concessionária vende mais",
    "qual concessionária fatura mais",
    "revenue",
    "sales",
)

VALUE_KEY = "vendas"
TIME_KEY = "periodo"
GRAIN = "month"
LABEL_KEY = "concessionaria"
DEFAULT_MEASURE = "vendas"
DEFAULT_DIMENSION = "concessionaria"
MEASURES = {
    "quantidade_os": {
        "label": "volume de OS",
        "kind": "count",
        "synonyms": ("volume", "volume de vendas", "total de OS", "quantidade de OS", "total de vendas"),
        "additive": True,
    },
    "vendas": {
        "label": "vendas",
        "kind": "money",
        "synonyms": ("vendas", "total vendas", "receita", "valor de vendas", "valor vendido"),
        "additive": True,
    },
    "ticket_medio_os": {
        "label": "ticket médio por OS",
        "kind": "money",
        "synonyms": ("ticket", "ticket médio", "ticket médio os", "média por OS", "ticket médio venda"),
        "additive": False,
    },
    "recebido": {
        "label": "recebido",
        "kind": "money",
        "synonyms": ("recebido", "recebimento", "recebimentos", "total recebido", "faturamento", "receita", "faturou"),
        "additive": True,
    },
    "percentual_recebido": {
        "label": "percentual recebido",
        "kind": "percent",
        "synonyms": ("percentual recebido", "percentual", "participação recebida", "share recebido"),
        "additive": False,
    },
}
DIMENSIONS = {
    "periodo": {
        "label": "período",
        "synonyms": ("período", "periodo", "mês", "mes", "competência", "competencia"),
    },
    "concessionaria": {
        "label": "concessionária",
        "synonyms": ("concessionária", "concessionaria", "loja", "unidade"),
    },
}
SUPPORTED_OPERATIONS = ("ranking_desc", "ranking_asc", "top_and_bottom", "list")

# 6 placeholders: estornos(date_from, date_to) + recebimentos(date_from, date_to) + OS criadas(date_from, date_to)
PARAMETERS = ("date_from", "date_to", "date_from", "date_to", "date_from", "date_to")
