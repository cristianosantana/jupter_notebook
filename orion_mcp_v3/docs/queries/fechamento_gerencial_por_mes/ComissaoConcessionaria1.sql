SET @ano = 2026;
SET @mes = 5; -- 0 = ano inteiro
SET @business_unit_id = 1; -- 0 = todas
SET @tipo_grupo_servico = 0; -- 0 completo, 1 sem couro, 2 couro

SELECT
    conc.nome AS concessionaria,
    SUM(IF(com.estorno IS NULL OR com.estorno != 1, oss.valor_venda_real, oss.valor_venda_real * -1)) AS total,
    SUM(IF(com.estorno IS NULL OR com.estorno != 1, com.valor_dentro + com.valor_fora, (com.valor_dentro + com.valor_fora) * -1)) AS total_comissao
FROM os
JOIN os_servicos AS oss ON oss.os_id = os.id
JOIN servicos AS serv ON serv.id = oss.servico_id
JOIN concessionarias AS conc ON os.concessionaria_id = conc.id
LEFT JOIN comissoes AS com
    ON com.comissionado_id = conc.id
    AND com.comissao_tipo_id = 1
    AND com.os_servico_id = oss.id
WHERE os.os_tipo_id IN (1, 2, 11)
  AND os.deleted_at IS NULL
  AND oss.deleted_at IS NULL
  AND com.deleted_at IS NULL
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
GROUP BY os.concessionaria_id
ORDER BY concessionaria;