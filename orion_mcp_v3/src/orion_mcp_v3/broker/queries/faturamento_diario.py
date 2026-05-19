"""
faturamento_diario
==================

Responde:
    - Quanto a empresa faturou por dia?
    - Qual a evolução diária de receita?
    - Qual o ticket médio diário?
    - Quanto foi recebido em cada forma de pagamento por dia?

Retorna:
    - data_recebimento (DATE)
    - total_recebimentos (INT)
    - valor_total_recebido (DECIMAL)
    - ticket_medio (DECIMAL)
    - total_dinheiro (DECIMAL) — caixa_tipo id=1
    - total_deposito (DECIMAL) — caixa_tipo id=2
    - total_credito (DECIMAL) — caixa_tipo id=3
    - total_cheque (DECIMAL) — caixa_tipo id=4
    - total_concessionaria (DECIMAL) — caixa_tipo id=5
    - total_debito (DECIMAL) — caixa_tipo id=6
    - total_pix (DECIMAL) — caixa_tipo id=7
    - total_permuta (DECIMAL) — caixa_tipo id=8
    - total_parcelamento (DECIMAL) — caixa_tipo id=9

Parâmetros:
    - date_from (str): data início — default últimos 30 dias
    - date_to (str): data fim — default hoje

Granularidade: day
Value key: valor_total_recebido
Time key: data_recebimento
"""

SQL = """\
SELECT
    DATE(cx.data_vencimento) AS data_recebimento,
    COUNT(*) AS total_recebimentos,
    ROUND(SUM(cx.valor), 2) AS valor_total_recebido,
    ROUND(AVG(cx.valor), 2) AS ticket_medio,
    ROUND(SUM(CASE WHEN ct.id = 1 THEN cx.valor ELSE 0 END), 2) AS total_dinheiro,
    ROUND(SUM(CASE WHEN ct.id = 2 THEN cx.valor ELSE 0 END), 2) AS total_deposito,
    ROUND(SUM(CASE WHEN ct.id = 3 THEN cx.valor ELSE 0 END), 2) AS total_credito,
    ROUND(SUM(CASE WHEN ct.id = 4 THEN cx.valor ELSE 0 END), 2) AS total_cheque,
    ROUND(SUM(CASE WHEN ct.id = 5 THEN cx.valor ELSE 0 END), 2) AS total_concessionaria,
    ROUND(SUM(CASE WHEN ct.id = 6 THEN cx.valor ELSE 0 END), 2) AS total_debito,
    ROUND(SUM(CASE WHEN ct.id = 7 THEN cx.valor ELSE 0 END), 2) AS total_pix,
    ROUND(SUM(CASE WHEN ct.id = 8 THEN cx.valor ELSE 0 END), 2) AS total_permuta,
    ROUND(SUM(CASE WHEN ct.id = 9 THEN cx.valor ELSE 0 END), 2) AS total_parcelamento
FROM caixas cx
    INNER JOIN os os ON os.id = cx.os_id
    INNER JOIN os_tipos ost ON ost.id = os.os_tipo_id
    INNER JOIN caixa_tipos ct ON ct.id = cx.caixa_tipo_id
WHERE
    cx.deleted_at IS NULL
    AND cx.cancelado = 0
    AND ost.ativo = 1
    AND cx.created_at >= %s AND cx.created_at < %s
GROUP BY DATE(cx.created_at)
ORDER BY created_at DESC"""

ANSWERS = (
    "faturamento diário",
    "receita por dia",
    "recebimentos por data",
    "quanto foi recebido por dia",
    "evolução diária de receita",
    "total cartão e pix por dia",
    "ticket médio diário",
    "revenue",
    "daily revenue",
    "ticket",
)

VALUE_KEY = "valor_total_recebido"
TIME_KEY = "data_recebimento"
GRAIN = "day"
LABEL_KEY = None
