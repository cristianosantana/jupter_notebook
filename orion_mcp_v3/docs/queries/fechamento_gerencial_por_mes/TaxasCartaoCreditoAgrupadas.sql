SET @ano = 2026;
SET @mes = 4; -- 0 = ano inteiro
SET @business_unit_id = 1; -- 0 = todas
SET @tipo_grupo_servico = 0; -- 0 completo, 1 sem couro, 2 couro

SELECT
    con_fin.empresa_id,
    em.nome AS empresa_nome,
    ROUND(SUM(con_fin.valor_bruto), 2) AS valor_bruto,
    ROUND(SUM(con_fin.valor_liquido), 2) AS valor_liquido,
    ROUND(MIN(con_fin.taxa), 2) AS min_taxa,
    ROUND(AVG(con_fin.taxa), 2) AS avg_taxa,
    ROUND(MAX(con_fin.taxa), 2) AS max_taxa,
    ROUND(SUM(con_fin.valor_bruto - con_fin.valor_liquido), 2) AS valor_taxa,
    COUNT(con_fin.id) AS quantidade_registros,
    LOWER(cax.bandeira_cartao) AS bandeira
FROM conciliacoes_financeira AS con_fin
JOIN empresas AS em ON con_fin.empresa_id = em.id
JOIN caixas AS cax ON con_fin.caixa_id = cax.id
WHERE YEAR(con_fin.data_transacao) = YEAR(DATE_SUB(STR_TO_DATE(CONCAT(@ano, '-', @mes, '-01'), '%Y-%m-%d'), INTERVAL 1 MONTH))
  AND MONTH(con_fin.data_transacao) = MONTH(DATE_SUB(STR_TO_DATE(CONCAT(@ano, '-', @mes, '-01'), '%Y-%m-%d'), INTERVAL 1 MONTH))
  AND con_fin.deleted_at IS NULL
GROUP BY empresa_id;