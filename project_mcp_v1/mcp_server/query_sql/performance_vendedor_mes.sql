-- Agregação MENSAL por vendedor × concessionária.
-- Coluna `periodo` = mês civil no formato YYYY-MM (derivado de os.created_at).
-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__ → filtram os.created_at.
SELECT 
    con.id AS concessionaria_id,
    con.nome AS concessionaria_nome,
    DATE_FORMAT(os.created_at, '%Y-%m') AS periodo,
    v.id AS vendedor_id,
    v.nome AS vendedor_nome,
    COUNT(DISTINCT os.id) AS qtd_os_fechadas,
    SUM(oss.valor_venda) AS faturamento_bruto,
    SUM(oss.valor_venda_real) AS faturamento_liquido,
    -- Ticket Médio (Valor real que o vendedor traz por cliente)
    ROUND(SUM(oss.valor_venda_real) / COUNT(DISTINCT os.id), 2) AS ticket_medio,
    -- Percentual de Desconto (Eficiência de negociação)
    ROUND(
        (1 - (SUM(oss.valor_venda_real) / SUM(oss.valor_venda))) * 100, 
        2
    ) AS perc_desconto_medio,
    -- Mix de Vendas: Quantos serviços o vendedor coloca em cada OS em média
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
    periodo, 
    v.id
ORDER BY 
    periodo DESC, 
    faturamento_liquido DESC;