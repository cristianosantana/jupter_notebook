SELECT 
    con.nome AS concessionaria,
    -- Tradução do número do dia para nome (1=Domingo, 2=Segunda...)
    DAYNAME(os.created_at) AS dia_semana,
    HOUR(os.created_at) AS hora_dia,
    s.nome AS servico,
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
    AND os.created_at >= DATE_SUB(NOW(), INTERVAL 6 MONTH) -- Analisamos os últimos 6 meses para ter padrão
GROUP BY 
    con.id, 
    DAYOFWEEK(os.created_at), 
    HOUR(os.created_at), 
    s.id
ORDER BY 
    con.nome, 
    DAYOFWEEK(os.created_at), 
    hora_dia, 
    qtd_vendas DESC;