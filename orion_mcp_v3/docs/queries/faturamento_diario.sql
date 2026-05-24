SELECT
    DATE(cx.data_pagamento) AS data_pagamento,
    COUNT(DISTINCT os.id) AS quantidade_os,
    ROUND(SUM(cx.valor - IFNULL(es.total_estorno, 0)), 2) AS valor_total_recebido,
    ROUND(AVG(cx.valor - IFNULL(es.total_estorno, 0)), 2) AS ticket_medio,
    ROUND(SUM(CASE WHEN ct.id = 1 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_dinheiro,
    ROUND(SUM(CASE WHEN ct.id = 2 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_deposito,
    ROUND(SUM(CASE WHEN ct.id = 3 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_credito,
    ROUND(SUM(CASE WHEN ct.id = 4 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_cheque,
    ROUND(SUM(CASE WHEN ct.id = 5 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_concessionaria,
    ROUND(SUM(CASE WHEN ct.id = 6 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_debito,
    ROUND(SUM(CASE WHEN ct.id = 7 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_pix,
    ROUND(SUM(CASE WHEN ct.id = 8 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_permuta,
    ROUND(SUM(CASE WHEN ct.id = 9 THEN cx.valor - IFNULL(es.total_estorno, 0) ELSE 0 END), 2) AS total_parcelamento
FROM caixas cx
INNER JOIN os os ON os.id = cx.os_id
INNER JOIN os_tipos ost ON ost.id = os.os_tipo_id
INNER JOIN caixa_tipos ct ON ct.id = cx.caixa_tipo_id
LEFT JOIN (
    SELECT  
        caixa_id, 
        SUM(valor) AS total_estorno
    FROM
        estornos
    WHERE
        status IN (3, 4) 
        AND deleted_at IS NULL
        AND created_at BETWEEN '2026-03-01 00:00:00' AND '2026-03-31 23:59:59'
    GROUP BY caixa_id
) es ON es.caixa_id = cx.id
WHERE
    cx.deleted_at IS NULL
    AND cx.cancelado = 0
    AND cx.valor > 0 -- Alinhado com a trava da primeira query
    AND ost.ativo = 1
    AND cx.data_pagamento BETWEEN '2026-03-01 00:00:00' AND '2026-03-31 23:59:59'
GROUP BY DATE(cx.data_pagamento)
ORDER BY cx.data_pagamento DESC;