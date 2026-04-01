-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__ → filtram oss.created_at.
-- Serviços em OS (linhas) vs OS fechadas: taxa de conversão global e por concessionária.
WITH Metricas_Por_Loja AS (
    SELECT
        c.id AS concessionaria_id,
        COUNT(DISTINCT oss.id) AS total_servicos,
        COUNT(DISTINCT CASE WHEN os.fechada = 1 THEN os.id END) AS total_convertidos
    FROM os_servicos oss
    LEFT JOIN os os ON oss.os_id = os.id
    INNER JOIN concessionarias c ON os.concessionaria_id = c.id
    WHERE oss.created_at BETWEEN __MCP_DATE_FROM__ AND __MCP_DATE_TO__
      AND oss.deleted_at IS NULL
    GROUP BY c.id
),
Totais_Globais AS (
    SELECT
        SUM(total_servicos) AS global_servicos,
        SUM(total_convertidos) AS global_convertidos
    FROM Metricas_Por_Loja
)
SELECT
    JSON_OBJECT(
        'periodo', CONCAT(DATE_FORMAT(__MCP_DATE_FROM__, '%d/%m/%Y'), ' a ', DATE_FORMAT(__MCP_DATE_TO__, '%d/%m/%Y')),
        'total_os_servicos', g.global_servicos,
        'os_servicos_convertidos_em_os_fechada', g.global_convertidos,
        'taxa_conversao_pct', ROUND((g.global_convertidos / NULLIF(g.global_servicos, 0)) * 100, 2),
        'por_concessionaria', (
            SELECT JSON_ARRAYAGG(
                JSON_OBJECT(
                    'concessionaria_id', concessionaria_id,
                    'os_servicos', total_servicos,
                    'convertidos', total_convertidos,
                    'taxa_pct', ROUND((total_convertidos / NULLIF(total_servicos, 0)) * 100, 2)
                )
            ) FROM Metricas_Por_Loja
        )
    ) AS resultado
FROM Totais_Globais g
