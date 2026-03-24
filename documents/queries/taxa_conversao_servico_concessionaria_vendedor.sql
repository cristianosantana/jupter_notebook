SELECT 
    con.nome AS concessionaria,
    v.nome AS vendedor,
    s.nome AS tipo_servico,
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
GROUP BY 
    con.id, 
    v.id, 
    s.id
ORDER BY 
    con.nome, 
    taxa_conversao_pct DESC;