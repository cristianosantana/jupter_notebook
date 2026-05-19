"""
performance_vendedor
=====================

Responde:
    - Quanto cada vendedor faturou no período?
    - Qual vendedor tem maior volume de vendas?
    - Qual o ranking de vendedores?
    - Qual o ticket médio por vendedor?
    - Qual a maior venda individual de cada vendedor?

Retorna:
    - vendedor (VARCHAR)
    - total_vendas (INT) — OS distintas
    - valor_total (DECIMAL)
    - ticket_medio (DECIMAL)
    - maior_venda (DECIMAL)

Parâmetros:
    - date_from (str): data início — default últimos 30 dias
    - date_to (str): data fim — default hoje

Granularidade: total (agregado no período)
Value key: valor_total
Time key: None
Label key: vendedor
"""

SQL = """\
SELECT
    LOWER(fu.nome) AS vendedor,
    COUNT(DISTINCT cx.os_id) AS total_vendas,
    ROUND(SUM(cx.valor), 2) AS valor_total,
    ROUND(AVG(cx.valor), 2) AS ticket_medio,
    ROUND(MAX(cx.valor), 2) AS maior_venda
FROM caixas cx
    INNER JOIN os os ON os.id = cx.os_id
    INNER JOIN funcionarios fu ON fu.id = os.vendedor_id
    INNER JOIN os_tipos ost ON ost.id = os.os_tipo_id
WHERE
    cx.deleted_at IS NULL
    AND ost.ativo = 1
    AND cx.data_vencimento >= %s AND cx.data_vencimento < %s
GROUP BY fu.nome
ORDER BY valor_total DESC"""

ANSWERS = (
    "volume de vendas",
    "maior volume de vendas",
    "faturamento por vendedor",
    "performance de vendedor",
    "ranking de vendedores",
    "qual vendedor vendeu mais",
    "ticket médio por vendedor",
    "vendas por vendedor",
    "revenue",
    "sales",
    "ticket",
)

VALUE_KEY = "valor_total"
TIME_KEY = None
GRAIN = "total"
LABEL_KEY = "vendedor"
