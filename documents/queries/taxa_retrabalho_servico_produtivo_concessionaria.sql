SELECT 
    con.nome AS concessionaria_nome,
    p_origem.nome AS produtivo_original,
    p_destino.nome AS produtivo_reparo,
    s.nome AS servico_reclamado,
    -- Usamos DISTINCT para não contar a mesma relação de retorno múltiplas vezes
    COUNT(DISTINCT ret.id) AS qtd_retrabalhos,
    MAX(ret.created_at) AS ultimo_retrabalho_registrado
FROM os_retornos ret
JOIN os os_orig ON ret.os_origem_id = os_orig.id
JOIN os os_dest ON ret.os_destino_id = os_dest.id
JOIN concessionarias con ON os_orig.concessionaria_id = con.id
-- Ligamos os serviços apenas da OS de DESTINO (o que foi refeito)
JOIN os_servicos oss_dest ON oss_dest.os_id = os_dest.id
JOIN servicos s ON oss_dest.servico_id = s.id
-- Buscamos o produtivo da OS de ORIGEM (quem errou) e do DESTINO (quem consertou)
JOIN os_servicos oss_orig ON oss_orig.os_id = os_orig.id 
    AND oss_orig.servico_id = oss_dest.servico_id -- Opcional: vincula o mesmo serviço
JOIN funcionarios p_origem ON oss_orig.produtivo_id = p_origem.id
JOIN funcionarios p_destino ON oss_dest.produtivo_id = p_destino.id
WHERE 
    os_orig.created_at >= DATE_SUB(NOW(), INTERVAL 90 DAY)
    AND os_orig.cancelada = 0
GROUP BY 
    con.id, 
    p_origem.id, 
    p_destino.id, 
    s.id
ORDER BY 
    ultimo_retrabalho_registrado DESC;