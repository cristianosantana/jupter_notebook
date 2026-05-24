SELECT 
    DATE_FORMAT(os.data_pagamento, '%Y-%m') AS periodo,
    COUNT(DISTINCT os.id) AS quantidade_os,
    ROUND(SUM(financeiro.recebido_total), 2) AS total,
    ROUND(SUM(financeiro.recebido_total) / COUNT(DISTINCT os.id),
            2) AS ticket_medio_os,
    ROUND(SUM(financeiro.recebido_dinheiro), 2) AS dinheiro,
    ROUND(SUM(financeiro.recebido_deposito), 2) AS deposito,
    ROUND(SUM(financeiro.recebido_credito), 2) AS cartao_credito,
    ROUND(SUM(financeiro.recebido_concessionaria),
            2) AS cortesia,
    ROUND(SUM(financeiro.recebido_pix), 2) AS pix,
    ROUND((SUM(financeiro.recebido_dinheiro) / SUM(financeiro.recebido_total)) * 100,
            2) AS percentual_dinheiro,
    ROUND((SUM(financeiro.recebido_deposito) / SUM(financeiro.recebido_total)) * 100,
            2) AS percentual_deposito,
    ROUND((SUM(financeiro.recebido_credito) / SUM(financeiro.recebido_total)) * 100,
            2) AS percentual_credito,
    ROUND((SUM(financeiro.recebido_concessionaria) / SUM(financeiro.recebido_total)) * 100,
            2) AS percentual_cortesia,
    ROUND((SUM(financeiro.recebido_pix) / SUM(financeiro.recebido_total)) * 100,
            2) AS percentual_pix
FROM
    os
        INNER JOIN
    os_tipos ost ON ost.id = os.os_tipo_id
        INNER JOIN
    (SELECT 
        cx.os_id,
            SUM(cx.valor - IFNULL(es.total_estorno, 0)) AS recebido_total,
            SUM(CASE
                WHEN ct.id = 1 THEN cx.valor - IFNULL(es.total_estorno, 0)
                ELSE 0
            END) AS recebido_dinheiro,
            SUM(CASE
                WHEN ct.id = 2 THEN cx.valor - IFNULL(es.total_estorno, 0)
                ELSE 0
            END) AS recebido_deposito,
            SUM(CASE
                WHEN ct.id = 3 THEN cx.valor - IFNULL(es.total_estorno, 0)
                ELSE 0
            END) AS recebido_credito,
            SUM(CASE
                WHEN ct.id = 5 THEN cx.valor - IFNULL(es.total_estorno, 0)
                ELSE 0
            END) AS recebido_concessionaria,
            SUM(CASE
                WHEN ct.id = 7 THEN cx.valor - IFNULL(es.total_estorno, 0)
                ELSE 0
            END) AS recebido_pix
    FROM
        caixas cx
    INNER JOIN caixa_tipos ct ON ct.id = cx.caixa_tipo_id
    LEFT JOIN (SELECT 
        caixa_id, SUM(valor) AS total_estorno
    FROM
        estornos
    WHERE
        status IN (3 , 4) AND deleted_at IS NULL
            AND created_at BETWEEN '2026-03-01 00:00:00' AND '2026-04-30 23:59:59'
    GROUP BY caixa_id) es ON es.caixa_id = cx.id
    WHERE
        cx.deleted_at IS NULL
            AND cx.cancelado = 0
            AND cx.valor > 0
    GROUP BY cx.os_id) financeiro ON financeiro.os_id = os.id
WHERE
    os.deleted_at IS NULL AND os.paga = 1
        AND ost.ativo = 1
        AND os.data_pagamento BETWEEN '2026-03-01 00:00:00' AND '2026-04-30 23:59:59'
GROUP BY DATE_FORMAT(os.data_pagamento, '%Y-%m')
ORDER BY periodo DESC;