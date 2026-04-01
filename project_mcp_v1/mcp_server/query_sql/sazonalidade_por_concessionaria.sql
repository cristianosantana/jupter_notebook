-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__ → filtram os.created_at.
WITH FaturamentoMensal AS (
    SELECT 
        con.id AS concessionaria_id,
        MONTH(os.created_at) AS mes_num,
        YEAR(os.created_at) AS ano_num,
        MAX(MONTHNAME(os.created_at)) AS mes_nome,
        SUM(oss.valor_venda_real) AS faturamento
    FROM os
    JOIN os_servicos oss ON oss.os_id = os.id
    JOIN concessionarias con ON os.concessionaria_id = con.id
    WHERE os.paga = 1 
    AND os.cancelada = 0
    AND os.created_at >= __MCP_DATE_FROM__
    AND os.created_at <= __MCP_DATE_TO__
    GROUP BY con.id, ano_num, mes_num
),
MediaHistoricaPorMes AS (
    -- Aqui calculamos a média de cada mês (Ex: Média de todos os meses 4)
    SELECT 
        concessionaria_id,
        mes_num,
        AVG(faturamento) AS media_historica_mes
    FROM FaturamentoMensal
    GROUP BY concessionaria_id, mes_num
)
SELECT 
    f.concessionaria_id,
    f.mes_num,
    f.mes_nome,
    f.ano_num,
    f.faturamento,
    ROUND(m.media_historica_mes, 2) AS media_esperada_para_este_mes,
    ROUND(((f.faturamento / m.media_historica_mes) - 1) * 100, 2) AS desvio_sazonal_pct
FROM FaturamentoMensal f
JOIN MediaHistoricaPorMes m ON f.concessionaria_id = m.concessionaria_id 
    AND f.mes_num = m.mes_num
ORDER BY f.ano_num DESC, f.mes_num DESC, f.concessionaria_id DESC;
