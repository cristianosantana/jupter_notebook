-- Agregação ANUAL por vendedor × concessionária (ano civil = YEAR(os.created_at)).
-- Coluna `periodo_ano` = ano com quatro dígitos (string 'YYYY').
-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__ → filtram os.created_at.
SELECT 
    con.id AS concessionaria_id,
    DATE_FORMAT(os.created_at, '%Y') AS periodo_ano,
    v.id AS vendedor_id,
    COUNT(DISTINCT os.id) AS qtd_os_fechadas,
    SUM(oss.valor_venda) AS faturamento_bruto,
    SUM(oss.valor_venda_real) AS faturamento_liquido,
    ROUND(SUM(oss.valor_venda_real) / COUNT(DISTINCT os.id), 2) AS ticket_medio,
    ROUND(
        (1 - (SUM(oss.valor_venda_real) / SUM(oss.valor_venda))) * 100, 
        2
    ) AS perc_desconto_medio,
    ROUND(COUNT(oss.id) / COUNT(DISTINCT os.id), 2) AS servicos_por_os
FROM os
JOIN os_servicos oss ON oss.os_id = os.id
JOIN funcionarios v ON os.vendedor_id = v.id 
JOIN concessionarias con ON os.concessionaria_id = con.id
WHERE 
    os.paga = 1 
    AND os.cancelada = 0
    AND os.created_at >= __MCP_DATE_FROM__
    AND os.created_at <= __MCP_DATE_TO__
    AND os.os_tipo_id IN(1,2,3,4,5)
GROUP BY 
    con.id, 
    periodo_ano, 
    v.id
ORDER BY 
    periodo_ano DESC, 
    faturamento_liquido DESC;
