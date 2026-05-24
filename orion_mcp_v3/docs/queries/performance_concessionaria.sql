SELECT  
    DATE_FORMAT(os.created_at, '%m/%Y') AS periodo,
    LOWER(co.nome) AS concessionaria,
    COUNT(DISTINCT os.id) AS quantidade_os,
    ROUND(SUM(COALESCE(os_vendas.valor_venda, 0)), 2) AS vendas,
    ROUND(SUM(COALESCE(os_vendas.valor_venda, 0)) / COUNT(DISTINCT os.id), 2) AS ticket_medio_os,
    ROUND(SUM(COALESCE(cx_recebido.valor_recebido, 0)), 2) AS recebido,
    ROUND((SUM(COALESCE(cx_recebido.valor_recebido, 0)) / IF(SUM(COALESCE(os_vendas.valor_venda, 0)) = 0, 1, SUM(COALESCE(os_vendas.valor_venda, 0)))) * 100, 2) AS percentual_recebido
FROM
    os os
LEFT JOIN
    (SELECT  
        oss.os_id, 
        SUM(oss.valor_venda_real) AS valor_venda
     FROM
        os_servicos oss
     WHERE
        oss.deleted_at IS NULL
        AND oss.cancelado = 0
     GROUP BY oss.os_id) os_vendas ON os_vendas.os_id = os.id
INNER JOIN
    concessionarias co ON co.id = os.concessionaria_id
LEFT JOIN
    (SELECT  
        cx.os_id, 
        SUM(cx.valor - IFNULL(es.total_estorno, 0)) AS valor_recebido
     FROM
        caixas cx
     LEFT JOIN (
        SELECT  
            caixa_id, 
            SUM(valor) AS total_estorno
        FROM
            estornos
        WHERE
            status IN (3, 4) 
            AND deleted_at IS NULL
            -- CONGELADO: Só abate o estorno se ele ocorreu em Março
            AND created_at BETWEEN '2026-03-01 00:00:00' AND '2026-03-31 23:59:59'
        GROUP BY caixa_id
     ) es ON es.caixa_id = cx.id
     WHERE
        cx.deleted_at IS NULL
        AND cx.cancelado = 0 
        AND cx.valor > 0
        AND cx.data_pagamento BETWEEN '2026-03-01 00:00:00' AND '2026-03-31 23:59:59'
     GROUP BY cx.os_id) cx_recebido ON cx_recebido.os_id = os.id
WHERE
    os.deleted_at IS NULL
    AND co.deleted_at IS NULL
    AND os.cancelada = 0
    AND os.os_tipo_id IN (1, 2, 5)
    AND os.created_at BETWEEN '2026-03-01 00:00:00' AND '2026-03-31 23:59:59'
GROUP BY DATE_FORMAT(os.created_at, '%m/%Y'), co.id, co.nome
ORDER BY periodo DESC, vendas DESC;