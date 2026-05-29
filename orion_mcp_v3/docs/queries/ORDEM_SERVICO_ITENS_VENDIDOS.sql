SELECT

    periodo,

    categoria,

    item,

    SUM(quantidade_vendida) AS quantidade_vendida,

    COUNT(DISTINCT os_id) AS quantidade_os,

    ROUND(SUM(vendas), 2) AS vendas,

    -- CORREÇÃO DO TICKET MÉDIO
    ROUND(
        SUM(vendas) / SUM(quantidade_vendida),
        2
    ) AS ticket_medio_item,

    ROUND(
        SUM(vendas)
        / COUNT(DISTINCT os_id),
        2
    ) AS ticket_medio_os,

    ROUND(
        (
            SUM(vendas)
            / SUM(SUM(vendas)) OVER(PARTITION BY periodo)
        ) * 100,
        2
    ) AS percentual_faturamento

FROM (

    -- SERVIÇOS
    SELECT

        os.id AS os_id,

        DATE_FORMAT(os.created_at, '%Y-%m') AS periodo,

        'servico' AS categoria,

        LOWER(ser.nome) AS item,

        COUNT(*) AS quantidade_vendida,

        SUM(oss.valor_venda_real) AS vendas

    FROM os

    INNER JOIN os_servicos oss
        ON oss.os_id = os.id

    LEFT JOIN servicos ser
        ON ser.id = oss.servico_id

    INNER JOIN os_tipos ost
        ON ost.id = os.os_tipo_id

    WHERE
        os.deleted_at IS NULL
        AND oss.deleted_at IS NULL

        AND os.cancelada = 0
        AND oss.cancelado = 0

        AND ost.ativo = 1

        AND os.created_at BETWEEN
            '2026-03-01 00:00:00'
            AND '2026-04-30 23:59:59'

    GROUP BY
        os.id,
        periodo,
        item

    UNION ALL

    -- PRODUTOS
    SELECT

        os.id AS os_id,

        DATE_FORMAT(os.created_at, '%Y-%m') AS periodo,

        'produto' AS categoria,

        LOWER(pr.nome) AS item,

        COUNT(*) AS quantidade_vendida,

        SUM(op.valor_venda_real) AS vendas

    FROM os

    INNER JOIN os_produtos op
        ON op.os_id = os.id

    LEFT JOIN produtos pr
        ON pr.id = op.produto_id

    INNER JOIN os_tipos ost
        ON ost.id = os.os_tipo_id

    WHERE
        os.deleted_at IS NULL
        AND op.deleted_at IS NULL

        AND os.cancelada = 0
        AND op.cancelado = 0

        AND ost.ativo = 1

        AND os.created_at BETWEEN
            '2026-03-01 00:00:00'
            AND '2026-04-30 23:59:59'

    GROUP BY
        os.id,
        periodo,
        item

) itens

GROUP BY
    periodo,
    categoria,
    item

ORDER BY
    periodo DESC,
    vendas DESC;