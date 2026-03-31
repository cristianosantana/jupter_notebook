-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__ → filtram os.created_at.
-- Top 5 e bottom 5 vendedores por ticket médio (OS fechadas).
WITH PerformanceVendedores AS (
    SELECT
        f.nome AS vendedor_nome,
        COUNT(DISTINCT os.id) AS qtd_vendas,
        ROUND(SUM(oss.valor_venda_real) / COUNT(DISTINCT os.id), 2) AS ticket_medio_real
    FROM os os
    INNER JOIN funcionarios f ON os.vendedor_id = f.id
    LEFT JOIN os_servicos oss ON os.id = oss.os_id
    WHERE os.created_at BETWEEN __MCP_DATE_FROM__ AND __MCP_DATE_TO__
      AND os.fechada = 1
      AND os.deleted_at IS NULL
      AND (oss.cancelado = 0 OR oss.cancelado IS NULL)
    GROUP BY f.id, f.nome
),
Rankeado AS (
    SELECT
        vendedor_nome,
        qtd_vendas,
        ticket_medio_real,
        ROW_NUMBER() OVER (ORDER BY ticket_medio_real DESC) AS ranking_top,
        ROW_NUMBER() OVER (ORDER BY ticket_medio_real ASC) AS ranking_bottom
    FROM PerformanceVendedores
)
SELECT JSON_OBJECT(
    'periodo', CONCAT(DATE_FORMAT(__MCP_DATE_FROM__, '%d/%m/%Y'), ' a ', DATE_FORMAT(__MCP_DATE_TO__, '%d/%m/%Y')),
    'top_vendedores', (
        SELECT JSON_ARRAYAGG(
            JSON_OBJECT(
                'ranking', ranking_top,
                'nome', vendedor_nome,
                'ticket_medio', ticket_medio_real,
                'qtd_vendas', qtd_vendas
            )
        ) FROM Rankeado WHERE ranking_top <= 5
    ),
    'bottom_vendedores', (
        SELECT JSON_ARRAYAGG(
            JSON_OBJECT(
                'ranking', ranking_bottom,
                'nome', vendedor_nome,
                'ticket_medio', ticket_medio_real,
                'qtd_vendas', qtd_vendas
            )
        ) FROM Rankeado WHERE ranking_bottom <= 5
    )
) AS resultado
