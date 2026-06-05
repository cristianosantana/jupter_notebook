SET @ano = 2026;
SET @mes = 4; -- 0 = ano inteiro
SET @business_unit_id = 1; -- 0 = todas
SET @tipo_grupo_servico = 0; -- 0 completo, 1 sem couro, 2 couro

SELECT
	DATE_FORMAT(os.data_pagamento, '%Y-%m') AS periodo,
    prod.id AS produto_id,
    prod.nome AS produto,
    COUNT(DISTINCT osp.id) AS quantidade,
    SUM(osp.valor_venda_real) AS total
FROM os
JOIN os_produtos AS osp ON osp.os_id = os.id
JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
JOIN produtos AS prod ON osp.produto_id = prod.id
WHERE os.os_tipo_id = 11
  AND os.deleted_at IS NULL
  AND osp.deleted_at IS NULL
  AND os.cancelada = 0
  AND osp.cancelado = 0
  AND os.paga = 1
  AND YEAR(os.data_pagamento) = @ano
  AND (@mes = 0 OR MONTH(os.data_pagamento) = @mes)
  AND (@business_unit_id = 0 OR conc.business_unit_id = @business_unit_id)
GROUP BY prod.id
ORDER BY prod.nome;