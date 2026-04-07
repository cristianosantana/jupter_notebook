/* @mcp_query_meta
resource_description: "Pares de serviços na mesma OS; ranking por concessionária e mês."
when_to_use: |
  Combo de serviços vendidos juntos, cross-sell, frequência de pares na mesma ordem de serviço.
output_shape: tabular_multiline
@mcp_query_meta */

-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__ → filtram os.created_at.
WITH ParesServicos AS (
    SELECT 
        con.id AS concessionaria_id,
        f.id AS vendedor_id,
        DATE_FORMAT(os.created_at, '%Y-%m') AS periodo,
        s1.id AS servico_A_id,
        s2.id AS servico_B_id,
        COUNT(*) AS frequencia_combo,
        SUM(oss1.valor_venda_real + oss2.valor_venda_real) AS receita_combo
    FROM os_servicos oss1
    JOIN os_servicos oss2 ON oss1.os_id = oss2.os_id 
        AND oss1.servico_id < oss2.servico_id 
    JOIN servicos s1 ON oss1.servico_id = s1.id
    JOIN servicos s2 ON oss2.servico_id = s2.id
    JOIN os ON oss1.os_id = os.id
    JOIN concessionarias con ON os.concessionaria_id = con.id
    JOIN funcionarios f ON os.vendedor_id = f.id
    WHERE 
        os.paga = 1 
        AND os.cancelada = 0
         AND os.created_at >= __MCP_DATE_FROM__
        AND os.created_at <= __MCP_DATE_TO__
    GROUP BY 
        con.id, periodo, s1.id, s2.id, f.id
)
SELECT 
    concessionaria_id,
    vendedor_id,
    periodo,
    servico_A_id,
    servico_B_id,
    frequencia_combo,
    receita_combo,
    -- Ranking para ver qual foi o combo campeão daquela unidade naquele mês específico
    RANK() OVER (PARTITION BY concessionaria_id, periodo ORDER BY frequencia_combo DESC) AS rank_mensal
FROM ParesServicos
WHERE frequencia_combo >= 1
ORDER BY periodo DESC, concessionaria_id ASC, rank_mensal ASC;
