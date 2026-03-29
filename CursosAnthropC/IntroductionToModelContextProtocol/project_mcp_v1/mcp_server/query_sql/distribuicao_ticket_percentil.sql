WITH TicketCalculado AS (
    SELECT 
        con.nome AS concessionaria_nome,
        con.id AS concessionaria_id,
        os.id AS os_id,
        SUM(oss.valor_venda_real) AS valor_total_os
    FROM os
    JOIN os_servicos oss ON oss.os_id = os.id
    JOIN concessionarias con ON os.concessionaria_id = con.id
    WHERE os.paga = 1 AND os.cancelada = 0
    AND os.created_at >= DATE_SUB(NOW(), INTERVAL 6 MONTH)
    GROUP BY con.id, os.id
),
Ranqueamento AS (
    SELECT 
        concessionaria_id,
        concessionaria_nome,
        valor_total_os,
        -- Divide as OSs em 4 grupos iguais por unidade
        NTILE(4) OVER (PARTITION BY concessionaria_id ORDER BY valor_total_os) AS quartil
    FROM TicketCalculado
)
SELECT 
    concessionaria_id,
    concessionaria_nome,
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