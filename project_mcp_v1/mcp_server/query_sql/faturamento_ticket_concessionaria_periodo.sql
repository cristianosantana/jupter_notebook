-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__ → filtram os.created_at.
SELECT 
    con.id AS concessionaria_id,
    con.nome AS concessionaria_nome,
    DATE_FORMAT(os.created_at, '%Y-%m') AS periodo,
    -- Faturamento Real de Mão de Obra
    SUM(oss.valor_venda_real) AS faturamento_servicos,
    -- Quantidade de Clientes Únicos Atendidos
    COUNT(DISTINCT os.id) AS qtd_os,
    -- Ticket Médio de Mão de Obra por OS
    ROUND(
        SUM(oss.valor_venda_real) / COUNT(DISTINCT os.id), 
        2
    ) AS ticket_medio_servico
FROM os
INNER JOIN os_servicos AS oss ON oss.os_id = os.id
INNER JOIN concessionarias con ON os.concessionaria_id = con.id
WHERE 
    os.paga = 1 
    AND os.cancelada = 0
    AND os.created_at >= __MCP_DATE_FROM__
    AND os.created_at <= __MCP_DATE_TO__
GROUP BY 
    con.id, 
    periodo 
ORDER BY 
    periodo DESC, 
    faturamento_servicos DESC;