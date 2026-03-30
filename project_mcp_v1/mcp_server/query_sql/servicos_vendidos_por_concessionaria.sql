SELECT 
    con.id AS concessionaria_id,
    con.nome AS concessionaria_nome,
    DATE_FORMAT(os.created_at, '%Y-%m') AS periodo,
    s.id AS servico_id,
    s.nome AS servico_nome,
    COUNT(DISTINCT os.id) AS qtd_os,
    SUM(oss.valor_venda) AS faturamento_bruto,
    SUM(oss.valor_venda_real) AS faturamento_liquido,
    -- Percentual de participação do serviço no faturamento daquela unidade naquele mês
    ROUND(
        (SUM(oss.valor_venda_real) / 
        SUM(SUM(oss.valor_venda_real)) OVER (PARTITION BY con.id, DATE_FORMAT(os.created_at, '%Y-%m'))) * 100, 
        2
    ) AS participacao_no_mes_pct
FROM os
JOIN os_servicos oss ON oss.os_id = os.id
JOIN servicos s ON oss.servico_id = s.id
JOIN concessionarias con ON os.concessionaria_id = con.id
WHERE 
    os.paga = 1 
    AND os.cancelada = 0
    -- Filtro dinâmico para os últimos 3 meses fechados + o mês atual
    AND os.created_at >= DATE_FORMAT(DATE_SUB(NOW(), INTERVAL 3 MONTH), '%Y-%m-01')
GROUP BY 
    con.id, 
    periodo, 
    s.id
ORDER BY 
    periodo DESC, 
    faturamento_liquido DESC;