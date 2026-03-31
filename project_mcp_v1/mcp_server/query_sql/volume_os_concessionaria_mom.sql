-- Período (obrigatório em run_analytics_query): __MCP_DATE_FROM__ .. __MCP_DATE_TO__ → filtram os.created_at.
-- Volume de OS por concessionária com variação MoM (último mês vs mês anterior no intervalo).
WITH Mensal_OS AS (
    SELECT
        c.id,
        c.nome,
        DATE_FORMAT(os.created_at, '%Y-%m-01') AS mes,
        COUNT(CASE WHEN os.deleted_at IS NULL THEN 1 END) AS qtd_total,
        SUM(CASE WHEN os.fechada = 0 AND os.paga = 0 THEN 1 ELSE 0 END) AS aberta,
        SUM(CASE WHEN os.fechada = 1 THEN 1 ELSE 0 END) AS fechada,
        SUM(CASE WHEN os.cancelada = 1 THEN 1 ELSE 0 END) AS cancelada
    FROM os
    INNER JOIN concessionarias c ON os.concessionaria_id = c.id
    WHERE os.deleted_at IS NULL AND os.created_at BETWEEN __MCP_DATE_FROM__ AND __MCP_DATE_TO__
    GROUP BY c.id, c.nome, mes
),
Totais AS (
    SELECT
        id,
        nome,
        SUM(qtd_total) AS total_geral,
        SUM(aberta) AS total_aberta,
        SUM(fechada) AS total_fechada,
        SUM(cancelada) AS total_cancelada
    FROM Mensal_OS
    GROUP BY id, nome
),
SerieComLag AS (
    SELECT
        id,
        nome,
        mes,
        qtd_total,
        LAG(qtd_total) OVER (PARTITION BY id ORDER BY mes) AS qtd_anterior
    FROM Mensal_OS
),
UltimoMes AS (
    SELECT s.id, s.nome, s.qtd_total, s.qtd_anterior
    FROM SerieComLag s
    INNER JOIN (
        SELECT id, MAX(mes) AS max_mes FROM SerieComLag GROUP BY id
    ) u ON s.id = u.id AND s.mes = u.max_mes
),
MoM AS (
    SELECT
        id,
        nome,
        ROUND(
            CASE
                WHEN qtd_anterior IS NULL OR qtd_anterior = 0 THEN NULL
                ELSE ((qtd_total - qtd_anterior) / qtd_anterior) * 100
            END,
            2
        ) AS variacao_mom
    FROM UltimoMes
)
SELECT
    JSON_OBJECT(
        'periodo', CONCAT(DATE_FORMAT(__MCP_DATE_FROM__, '%d/%m/%Y'), ' a ', DATE_FORMAT(__MCP_DATE_TO__, '%d/%m/%Y')),
        'concessionarias', JSON_ARRAYAGG(
            JSON_OBJECT(
                'id', t.id,
                'nome', t.nome,
                'qtd_os_total', t.total_geral,
                'qtd_aberta', t.total_aberta,
                'qtd_fechada', t.total_fechada,
                'qtd_cancelada', t.total_cancelada,
                'taxa_cancelamento_pct', ROUND((t.total_cancelada / NULLIF(t.total_geral, 0)) * 100, 2),
                'variacao_mom_pct', COALESCE(m.variacao_mom, 0)
            )
        )
    ) AS resultado
FROM Totais t
LEFT JOIN MoM m ON t.id = m.id AND t.nome = m.nome
