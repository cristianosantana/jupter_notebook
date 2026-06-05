SET @ano = 2026;
SET @mes = 4; -- 0 = ano inteiro
SET @business_unit_id = 1; -- 0 = todas
SET @tipo_grupo_servico = 0; -- 0 completo, 1 sem couro, 2 couro

SELECT
    ost.id,
    ost.nome AS os_tipo,
    DATE_FORMAT(os.data_pagamento, '%Y-%m') AS periodo,
    SUM(osp.valor_venda_real) AS total
FROM os
JOIN os_produtos AS osp ON osp.os_id = os.id
JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
JOIN os_tipos AS ost ON os.os_tipo_id = ost.id
WHERE os.os_tipo_id = 11
  AND os.deleted_at IS NULL
  AND osp.deleted_at IS NULL
  AND ost.deleted_at IS NULL
  AND os.cancelada = 0
  AND osp.cancelado = 0
  AND os.paga = 1
  AND YEAR(os.data_pagamento) = @ano
  AND (@mes = 0 OR MONTH(os.data_pagamento) = @mes)
  AND (@business_unit_id = 0 OR conc.business_unit_id = @business_unit_id)
GROUP BY ost.id
ORDER BY ost.id;