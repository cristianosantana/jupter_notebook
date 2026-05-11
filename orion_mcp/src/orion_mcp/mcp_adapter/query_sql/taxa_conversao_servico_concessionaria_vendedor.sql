/* @mcp_query_meta
resource_description: "Conversão de serviço por concessionária e vendedor."
when_to_use: |
  Taxa de conversão de proposta/orçamento em venda de serviço, desempenho do vendedor.
output_shape: tabular_multiline
@mcp_query_meta */

-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__ → filtram os.created_at.
SELECT 
    con.id AS concessionaria_id,
    v.id AS vendedor_id,
    s.id AS servico_id,
    COUNT(DISTINCT os.id) AS total_oportunidades_os,
    SUM(CASE WHEN os.paga = 1 AND os.cancelada = 0 THEN 1 ELSE 0 END) AS total_conversoes,
    ROUND(
        (SUM(CASE WHEN os.paga = 1 AND os.cancelada = 0 THEN 1 ELSE 0 END) / COUNT(DISTINCT os.id)) * 100, 
        2
    ) AS taxa_conversao_pct
FROM os
JOIN concessionarias con ON os.concessionaria_id = con.id
JOIN funcionarios v ON os.vendedor_id = v.id -- Assumindo que vendedor_id está na tabela os
JOIN os_servicos oss ON oss.os_id = os.id
JOIN servicos s ON oss.servico_id = s.id
WHERE os.created_at >= __MCP_DATE_FROM__
    AND os.created_at <= __MCP_DATE_TO__
GROUP BY 
    con.id, 
    v.id, 
    s.id
ORDER BY 
    con.id, 
    taxa_conversao_pct DESC;
