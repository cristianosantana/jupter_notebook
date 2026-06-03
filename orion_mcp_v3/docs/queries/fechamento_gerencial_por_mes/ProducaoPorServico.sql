SET @ano = 2026;
SET @mes = 5; -- 0 = ano inteiro
SET @business_unit_id = 1; -- 0 = todas
SET @tipo_grupo_servico = 0; -- 0 completo, 1 sem couro, 2 couro

SELECT
    serv.id AS servico_id,
    serv.nome AS servico,
    COUNT(DISTINCT oss.id) AS quantidade,
    SUM(oss.valor_venda_real) AS total,
    serv.custo_fixo AS custo
FROM os
JOIN os_servicos AS oss ON oss.os_id = os.id
JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
JOIN servicos AS serv ON oss.servico_id = serv.id
WHERE os.os_tipo_id IN (1, 2, 3, 4, 5)
  AND os.deleted_at IS NULL
  AND oss.deleted_at IS NULL
  AND os.cancelada = 0
  AND oss.cancelado = 0
  AND os.paga = 1
  AND YEAR(os.data_pagamento) = @ano
  AND (@mes = 0 OR MONTH(os.data_pagamento) = @mes)
  AND (@business_unit_id = 0 OR conc.business_unit_id = @business_unit_id)
  AND (
      @tipo_grupo_servico = 0
      OR (@tipo_grupo_servico = 1 AND serv.grupo_servico_id != 3)
      OR (@tipo_grupo_servico = 2 AND serv.grupo_servico_id = 3)
  )
GROUP BY serv.id
ORDER BY serv.nome;