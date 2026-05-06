/* @mcp_query_meta
resource_description: "Propensão de compra por hora, dia da semana e tipo de serviço."
when_to_use: |
  Melhor hora/dia para vender, padrão temporal de compra por serviço.
output_shape: tabular_multiline
@mcp_query_meta */

-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__ → filtram os.created_at.
SELECT 
    con.id AS concessionaria_id,
    -- Tradução do número do dia para nome (1=Domingo, 2=Segunda...)
    DAYNAME(os.created_at) AS dia_semana,
    HOUR(os.created_at) AS hora_dia,
    s.id AS servico_id,
    COUNT(DISTINCT os.id) AS qtd_vendas,
    SUM(oss.valor_venda_real) AS faturamento_total,
    -- Ranking para identificar o serviço "campeão" naquele horário
    RANK() OVER (PARTITION BY con.id, DAYOFWEEK(os.created_at), HOUR(os.created_at) 
                 ORDER BY COUNT(DISTINCT os.id) DESC) AS ranking_servico
FROM os
JOIN concessionarias con ON os.concessionaria_id = con.id
JOIN os_servicos oss ON oss.os_id = os.id
JOIN servicos s ON oss.servico_id = s.id
WHERE 
    os.paga = 1 
    AND os.cancelada = 0
    AND os.created_at >= __MCP_DATE_FROM__
    AND os.created_at <= __MCP_DATE_TO__
GROUP BY 
    con.id, 
    DAYOFWEEK(os.created_at), 
    HOUR(os.created_at), 
    s.id
ORDER BY 
    con.id, 
    DAYOFWEEK(os.created_at), 
    hora_dia, 
    qtd_vendas DESC;
