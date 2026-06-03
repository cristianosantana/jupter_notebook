SET @ano = 2026;
SET @mes = 5; -- 0 = ano inteiro
SET @business_unit_id = 1; -- 0 = todas
SET @tipo_grupo_servico = 0; -- 0 completo, 1 sem couro, 2 couro
SET @caixa_tipo_id = 3;
SET @empresa_faturamento_id = 0;

SELECT
    CONCAT(cx.quant_parcelas, 'X') AS parcelas,
    cx.quant_parcelas AS quant_parcelas,
    COUNT(DISTINCT os.id) AS quantidade,
    SUM(
        cx.valor - IFNULL((
            SELECT SUM(valor)
            FROM estornos
            WHERE caixa_id = cx.id
              AND status IN (3, 4)
              AND deleted_at IS NULL
        ), 0)
    ) AS total
FROM os
JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
JOIN caixas AS cx ON cx.os_id = os.id
WHERE os.os_tipo_id IN (1, 2, 3, 4, 5, 11)
  AND os.deleted_at IS NULL
  AND cx.deleted_at IS NULL
  AND os.cancelada = 0
  AND os.paga = 1
  AND cx.caixa_tipo_id = @caixa_tipo_id
  AND YEAR(os.data_pagamento) = @ano
  AND (@empresa_faturamento_id = 0 OR cx.empresa_faturamento_id = @empresa_faturamento_id)
  AND (@mes = 0 OR MONTH(os.data_pagamento) = @mes)
  AND (@business_unit_id = 0 OR conc.business_unit_id = @business_unit_id)
GROUP BY cx.quant_parcelas
ORDER BY cx.quant_parcelas;