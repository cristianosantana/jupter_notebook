WITH ParesServicos AS (
    SELECT 
        con.id AS concessionaria_id,
        con.nome AS concessionaria_nome,
        DATE_FORMAT(os.created_at, '%Y-%m') AS periodo,
        s1.id AS servico_A_id,
        s1.nome AS servico_A_nome,
        s2.id AS servico_B_id,
        s2.nome AS servico_B_nome,
        COUNT(*) AS frequencia_combo,
        SUM(oss1.valor_venda_real + oss2.valor_venda_real) AS receita_combo
    FROM os_servicos oss1
    JOIN os_servicos oss2 ON oss1.os_id = oss2.os_id 
        AND oss1.servico_id < oss2.servico_id 
    JOIN servicos s1 ON oss1.servico_id = s1.id
    JOIN servicos s2 ON oss2.servico_id = s2.id
    JOIN os ON oss1.os_id = os.id
    JOIN concessionarias con ON os.concessionaria_id = con.id
    WHERE 
        os.paga = 1 
        AND os.cancelada = 0
        AND os.created_at >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
    GROUP BY 
        con.id, periodo, s1.id, s2.id
)
SELECT 
    concessionaria_id,
    concessionaria_nome,
    periodo,
    servico_A_id,
    servico_A_nome,
    servico_B_id,
    servico_B_nome,
    frequencia_combo,
    receita_combo,
    -- Ranking para ver qual foi o combo campeão daquela unidade naquele mês específico
    RANK() OVER (PARTITION BY concessionaria_id, periodo ORDER BY frequencia_combo DESC) AS rank_mensal
FROM ParesServicos
WHERE frequencia_combo >= 1 -- AND periodo = '2026-01' AND servico_A_nome = 'CLEAR COMFORT PARABRISA' AND servico_B_nome = 'FILME DE SEGURANÇA PS4'
ORDER BY periodo DESC, concessionaria_id ASC, rank_mensal ASC;