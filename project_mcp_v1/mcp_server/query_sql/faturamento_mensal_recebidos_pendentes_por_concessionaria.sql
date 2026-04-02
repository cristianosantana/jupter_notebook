-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__
-- filtram mes_referencia (competência YYYY-MM). Uma linha por mês e concessionária.
WITH FaturamentoBase AS (
    SELECT
        c.os_id,
        c.valor,
        'Recebido' AS status_faturamento,
        DATE_FORMAT(
            COALESCE(cp.data_vencimento, cp.created_at, c.data_pagamento, c.created_at),
            '%Y-%m'
        ) AS mes_referencia,
        con.nome AS nome_concessionaria
    FROM caixas c
    LEFT JOIN caixas_pendentes cp ON c.caixa_pendente_id = cp.id
    INNER JOIN os o ON c.os_id = o.id
    INNER JOIN concessionarias con ON o.concessionaria_id = con.id
    WHERE c.cancelado = 0
      AND c.deleted_at IS NULL

    UNION ALL

    SELECT
        cp.os_id,
        cp.valor,
        'Pendente' AS status_faturamento,
        DATE_FORMAT(COALESCE(cp.data_vencimento, cp.created_at), '%Y-%m') AS mes_referencia,
        con.nome AS nome_concessionaria
    FROM caixas_pendentes cp
    LEFT JOIN caixas c
        ON c.caixa_pendente_id = cp.id
       AND c.cancelado = 0
       AND c.deleted_at IS NULL
    INNER JOIN os o ON cp.os_id = o.id
    INNER JOIN concessionarias con ON o.concessionaria_id = con.id
    WHERE cp.cancelado = 0
      AND cp.deleted_at IS NULL
      AND c.id IS NULL
)
SELECT
    mes_referencia AS `Mês de Referência (Competência)`,
    nome_concessionaria AS `Concessionária`,
    COUNT(DISTINCT os_id) AS `Qtd. Ordens de Serviço (OS)`,
    SUM(CASE WHEN status_faturamento = 'Recebido' THEN valor ELSE 0 END) AS `Total Recebido (R$)`,
    SUM(CASE WHEN status_faturamento = 'Pendente' THEN valor ELSE 0 END) AS `Total Pendente (R$)`,
    SUM(valor) AS `Faturamento Total Previsto (R$)`
FROM FaturamentoBase
WHERE mes_referencia >= DATE_FORMAT(__MCP_DATE_FROM__, '%Y-%m')
  AND mes_referencia <= DATE_FORMAT(__MCP_DATE_TO__, '%Y-%m')
GROUP BY mes_referencia, nome_concessionaria
ORDER BY mes_referencia DESC, `Faturamento Total Previsto (R$)` DESC;
