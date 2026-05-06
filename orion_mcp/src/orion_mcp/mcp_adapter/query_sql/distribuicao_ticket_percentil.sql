/* @mcp_query_meta
resource_description: "Distribuição de ticket por quartis (NTILE) por concessionária."
when_to_use: |
  Segmentação por tamanho de ticket, quartis, perfil premium vs baixo ticket.
output_shape: tabular_multiline
@mcp_query_meta */

-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__ → filtram os.created_at.
WITH TicketCalculado AS (
    SELECT 
        con.id AS concessionaria_id,
        os.id AS os_id,
        SUM(oss.valor_venda_real) AS valor_total_os
    FROM os
    JOIN os_servicos oss ON oss.os_id = os.id
    JOIN concessionarias con ON os.concessionaria_id = con.id
    WHERE os.paga = 1 AND os.cancelada = 0
    AND os.created_at >= __MCP_DATE_FROM__
    AND os.created_at <= __MCP_DATE_TO__
    GROUP BY con.id, os.id
),
Ranqueamento AS (
    SELECT 
        concessionaria_id,
        valor_total_os,
        -- Divide as OSs em 4 grupos iguais por unidade
        NTILE(4) OVER (PARTITION BY concessionaria_id ORDER BY valor_total_os) AS quartil
    FROM TicketCalculado
)
SELECT 
    concessionaria_id,
    CASE 
        WHEN quartil = 1 THEN '25% (Tickets Baixos)'
        WHEN quartil = 2 THEN '50% (Mediana)'
        WHEN quartil = 3 THEN '75% (Tickets Altos)'
        WHEN quartil = 4 THEN '100% (Premium)'
    END AS faixa_percentil,
    ROUND(MIN(valor_total_os), 2) AS valor_minimo,
    ROUND(MAX(valor_total_os), 2) AS valor_maximo,
    COUNT(*) AS qtd_os_na_faixa
FROM Ranqueamento
GROUP BY concessionaria_id, quartil
ORDER BY concessionaria_id, quartil;
