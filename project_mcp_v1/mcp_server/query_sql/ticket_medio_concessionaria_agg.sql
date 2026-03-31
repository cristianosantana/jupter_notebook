-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__ → filtram os.created_at.
-- Ticket médio e estatísticas por concessionária (OS fechadas, linhas de serviço fechadas).
WITH Valor_Por_OS AS (
    SELECT
        os.id AS os_id,
        os.concessionaria_id,
        SUM(oss.valor_venda_real) AS valor_total_os
    FROM os
    LEFT JOIN os_servicos oss ON os.id = oss.os_id
    WHERE os.created_at BETWEEN __MCP_DATE_FROM__ AND __MCP_DATE_TO__
      AND os.fechada = 1
      AND oss.fechado = 1
      AND oss.cancelado = 0
      AND os.deleted_at IS NULL
    GROUP BY os.id, os.concessionaria_id
),
Metricas_Concessionaria AS (
    SELECT
        c.id,
        c.nome,
        COUNT(vpos.os_id) AS qtd_vendas,
        SUM(vpos.valor_total_os) AS faturamento_total,
        AVG(vpos.valor_total_os) AS ticket_medio,
        MIN(vpos.valor_total_os) AS ticket_min,
        MAX(vpos.valor_total_os) AS ticket_max,
        STDDEV_POP(vpos.valor_total_os) AS desvio_padrao
    FROM concessionarias c
    INNER JOIN Valor_Por_OS vpos ON c.id = vpos.concessionaria_id
    GROUP BY c.id, c.nome
)
SELECT
    JSON_OBJECT(
        'periodo', CONCAT(DATE_FORMAT(__MCP_DATE_FROM__, '%d/%m/%Y'), ' a ', DATE_FORMAT(__MCP_DATE_TO__, '%d/%m/%Y')),
        'concessionarias', JSON_ARRAYAGG(
            JSON_OBJECT(
                'id', id,
                'nome', nome,
                'qtd_vendas', qtd_vendas,
                'ticket_medio', ROUND(ticket_medio, 2),
                'ticket_min', ROUND(ticket_min, 2),
                'ticket_max', ROUND(ticket_max, 2),
                'desvio_padrao', ROUND(desvio_padrao, 2),
                'faturamento_total', ROUND(faturamento_total, 2)
            )
        )
    ) AS resultado
FROM Metricas_Concessionaria
