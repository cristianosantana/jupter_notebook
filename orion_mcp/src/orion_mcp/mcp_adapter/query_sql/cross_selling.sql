/* @mcp_query_meta
resource_description: "Pares de serviços na mesma OS; ranking por concessionária e mês."
when_to_use: |
  Combo de serviços vendidos juntos, cross-sell, frequência de pares na mesma ordem de serviço.
output_shape: tabular_multiline
@mcp_query_meta */

-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__ → filtram os.created_at.
WITH ParesUnicos AS (
    SELECT DISTINCT
        os.id AS os_id,
        con.id AS concessionaria_id,
        f.id AS vendedor_id,
        DATE_FORMAT(os.created_at, '%Y-%m') AS periodo,
        oss1.servico_id AS servico_A_id,
        oss2.servico_id AS servico_B_id,
        oss1.valor_venda_real as valor_venda_real_servico_A,
        oss2.valor_venda_real as valor_venda_real_servico_B
    FROM os_servicos oss1
    JOIN os_servicos oss2 
        ON oss1.os_id = oss2.os_id 
        AND oss1.servico_id < oss2.servico_id
    JOIN os ON os.id = oss1.os_id
    JOIN concessionarias con ON os.concessionaria_id = con.id
    JOIN funcionarios f ON os.vendedor_id = f.id
    WHERE 
        os.paga = 1 
        AND os.cancelada = 0
        AND os.created_at >= __MCP_DATE_FROM__
        AND os.created_at < __MCP_DATE_TO__
)

SELECT
    concessionaria_id,
    vendedor_id,
    periodo,
    servico_A_id,
    servico_B_id,
    COUNT(*) AS frequencia_combo,
    SUM(valor_venda_real_servico_A + valor_venda_real_servico_B) AS receita_combo
FROM ParesUnicos
GROUP BY 
    concessionaria_id,
    vendedor_id,
    periodo,
    servico_A_id,
    servico_B_id;