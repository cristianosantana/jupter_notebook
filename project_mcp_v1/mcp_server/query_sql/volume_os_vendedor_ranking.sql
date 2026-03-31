-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__ → filtram os.created_at.
-- Volume de OS por vendedor e concessionária com ranking global por total_os.
WITH MetricasVendedores AS (
    SELECT
        f.id AS vendedor_id,
        f.nome AS vendedor_nome,
        c.nome AS concessionaria_nome,
        COUNT(DISTINCT os.id) AS total_os,
        SUM(CASE WHEN os.fechada THEN 1 ELSE 0 END) AS fechadas,
        SUM(CASE WHEN os.cancelada THEN 1 ELSE 0 END) AS canceladas
    FROM os os
    INNER JOIN funcionarios f ON os.vendedor_id = f.id
    INNER JOIN concessionarias c ON os.concessionaria_id = c.id
    WHERE os.created_at BETWEEN __MCP_DATE_FROM__ AND __MCP_DATE_TO__
      AND os.deleted_at IS NULL
    GROUP BY f.id, f.nome, c.id, c.nome
),
Ranked AS (
    SELECT
        *,
        ROW_NUMBER() OVER (ORDER BY total_os DESC) AS posicao_ranking
    FROM MetricasVendedores
)
SELECT
    JSON_OBJECT(
        'periodo', CONCAT(DATE_FORMAT(__MCP_DATE_FROM__, '%d/%m/%Y'), ' a ', DATE_FORMAT(__MCP_DATE_TO__, '%d/%m/%Y')),
        'vendedores', JSON_ARRAYAGG(
            JSON_OBJECT(
                'ranking', posicao_ranking,
                'id', vendedor_id,
                'nome', vendedor_nome,
                'concessionaria', concessionaria_nome,
                'qtd_os', total_os,
                'qtd_fechada', fechadas,
                'qtd_cancelada', canceladas,
                'taxa_fechamento_pct', ROUND((fechadas / NULLIF(total_os, 0)) * 100, 2)
            )
        )
    ) AS resultado
FROM Ranked
