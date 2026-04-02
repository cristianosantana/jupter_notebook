-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__
-- filtram mes_referencia (competência YYYY-MM a partir de caixas / caixas_pendentes).
WITH FaturamentoBase AS (
    SELECT
        c.os_id,
        c.valor,
        'Recebido' AS status_faturamento,
        DATE_FORMAT(
            COALESCE(cp.data_vencimento, cp.created_at, c.data_pagamento, c.created_at),
            '%Y-%m'
        ) AS mes_referencia
    FROM caixas c
    LEFT JOIN caixas_pendentes cp ON c.caixa_pendente_id = cp.id
    WHERE c.cancelado = 0
      AND c.deleted_at IS NULL

    UNION ALL

    SELECT
        cp.os_id,
        cp.valor,
        'Pendente' AS status_faturamento,
        DATE_FORMAT(COALESCE(cp.data_vencimento, cp.created_at), '%Y-%m') AS mes_referencia
    FROM caixas_pendentes cp
    LEFT JOIN caixas c
        ON c.caixa_pendente_id = cp.id
       AND c.cancelado = 0
       AND c.deleted_at IS NULL
    WHERE cp.cancelado = 0
      AND cp.deleted_at IS NULL
      AND c.id IS NULL
)
SELECT
    mes_referencia AS `Mês de Referência (Competência)`,
    COUNT(DISTINCT os_id) AS `Qtd. Ordens de Serviço (OS)`,
    SUM(CASE WHEN status_faturamento = 'Recebido' THEN valor ELSE 0 END) AS `Total Recebido (R$)`,
    SUM(CASE WHEN status_faturamento = 'Pendente' THEN valor ELSE 0 END) AS `Total Pendente (R$)`,
    SUM(valor) AS `Faturamento Total Previsto (R$)`
FROM FaturamentoBase
WHERE mes_referencia >= DATE_FORMAT(__MCP_DATE_FROM__, '%Y-%m')
  AND mes_referencia <= DATE_FORMAT(__MCP_DATE_TO__, '%Y-%m')
GROUP BY mes_referencia
ORDER BY mes_referencia DESC;
