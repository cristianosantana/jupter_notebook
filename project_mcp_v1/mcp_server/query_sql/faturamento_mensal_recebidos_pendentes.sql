/* @mcp_query_meta
resource_description: "Por mês de competência (YYYY-MM): OS distintas, total recebido (caixas), total pendente (promessas sem caixa) e faturamento total previsto (recebido + pendente), a partir de caixas/caixas_pendentes."
when_to_use: |
  Lista detalhada do que consegue responder ao interpretar o resultado desta query. 1) Visão geral de faturamento (macro): quanto a empresa produziu/vendeu num mês (coluna «Faturamento Total Previsto» — serviços da competência, pago na hora + a receber); evolução vs meses anteriores (uma linha por mês, do mais recente ao mais antigo). 2) Inadimplência e recebíveis: quanto já entrou no caixa (Total Recebido) vs. valor ainda na rua — promessas não quitadas (Total Pendente); leitura da proporção pendente face ao faturamento. 3) Volume operacional: quantas OS únicas geraram cobrança no mês (sem duplicar por pagamentos parciais). KPIs derivados (conta ou Excel): ticket médio mensal = Faturamento Total Previsto ÷ Qtd. OS; taxa de conversão de recebimento = (Total Recebido ÷ Faturamento Total Previsto) × 100; taxa de pendência/inadimplência = (Total Pendente ÷ Faturamento Total Previsto) × 100.
output_shape: tabular_multiline
not_confused_with:
  - faturamento_ticket_concessionaria_periodo
  - faturamento_mensal_recebidos_pendentes_por_concessionaria
@mcp_query_meta */

-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__
-- filtram mes_referencia (competência YYYY-MM a partir de caixas / caixas_pendentes).
WITH FaturamentoBase AS (
    SELECT
        c.os_id,
        c.valor,
        'Recebido' AS status_faturamento,
        DATE_FORMAT(c.created_at,'%Y-%m') AS mes_referencia
    FROM caixas c
    LEFT JOIN caixas_pendentes cp ON c.caixa_pendente_id = cp.id
    WHERE c.cancelado = 0
      AND c.deleted_at IS NULL

    UNION ALL

    SELECT
        cp.os_id,
        cp.valor,
        'Pendente' AS status_faturamento,
        DATE_FORMAT(cp.created_at, '%Y-%m') AS mes_referencia
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
