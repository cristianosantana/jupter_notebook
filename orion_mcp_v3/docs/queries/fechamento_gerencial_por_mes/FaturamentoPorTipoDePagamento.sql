SET @ano = 2026;
SET @mes = 3; -- 0 = ano inteiro
SET @business_unit_id = 1; -- 0 = todas
SET @tipo_grupo_servico = 0; -- 0 completo, 1 sem couro, 2 couro

SELECT 
    ct.id AS caixa_tipo_id,
    ct.nome AS caixa_tipo,
    DATE_FORMAT(CONCAT(@ano, '-', @mes, '-01'), '%Y-%m') AS periodo,
    -- Coalesce garante que se não houver registros, o valor retornado seja 0 em vez de NULL
    COALESCE(p.total_pagamentos, 0) AS total_pagamentos,
    COALESCE(e.total_estornos, 0) AS total_estornos,
    (COALESCE(p.total_pagamentos, 0) - COALESCE(e.total_estornos, 0)) AS total_liquido
FROM caixa_tipos ct

-- Subquery de Pagamentos agrupada por tipo
LEFT JOIN (
    SELECT 
        cx.caixa_tipo_id,
        SUM(cx.valor) AS total_pagamentos
    FROM caixas AS cx
    INNER JOIN os ON cx.os_id = os.id
    INNER JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
    WHERE os.deleted_at IS NULL
      AND cx.deleted_at IS NULL
      AND os.os_tipo_id IN (1, 2, 3, 4, 5, 11)
      AND os.cancelada = 0
      AND os.paga = 1
      AND YEAR(os.data_pagamento) = @ano
      AND (@mes = 0 OR MONTH(os.data_pagamento) = @mes)
      AND (@business_unit_id = 0 OR conc.business_unit_id = @business_unit_id)
    GROUP BY cx.caixa_tipo_id
) p ON ct.id = p.caixa_tipo_id

-- Subquery de Estornos agrupada por tipo
LEFT JOIN (
    SELECT 
        cx.caixa_tipo_id,
        SUM(est.valor) AS total_estornos
    FROM estornos AS est
    INNER JOIN caixas AS cx ON est.caixa_id = cx.id
    INNER JOIN os ON cx.os_id = os.id
    INNER JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
    WHERE os.deleted_at IS NULL
      AND est.deleted_at IS NULL
      AND cx.deleted_at IS NULL
      AND est.status > 2
      AND os.os_tipo_id IN (1, 2, 3, 4, 5, 11) -- Nota: mantido sem o 11 conforme sua regra original
      AND os.cancelada = 0
      AND YEAR(est.updated_at) = @ano
      AND (@mes = 0 OR MONTH(est.updated_at) = @mes)
      AND (@business_unit_id = 0 OR conc.business_unit_id = @business_unit_id)
    GROUP BY cx.caixa_tipo_id
) e ON ct.id = e.caixa_tipo_id

WHERE ct.ativo = 1
ORDER BY ct.id;