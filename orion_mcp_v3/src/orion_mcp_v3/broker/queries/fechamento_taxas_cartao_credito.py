"""
fechamento_taxas_cartao_credito
===============================

Taxas de cartao de credito agrupadas por empresa.

A query documental original calcula o mes anterior ao fechamento. Aqui o mesmo
comportamento e preservado deslocando `date_from` e `date_to` em um mes.
"""

SQL = """\
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
WHERE con_fin.data_transacao >= DATE_SUB(%s, INTERVAL 1 MONTH)
  AND con_fin.data_transacao < DATE_SUB(DATE_ADD(%s, INTERVAL 1 DAY), INTERVAL 1 MONTH)
  AND con_fin.deleted_at IS NULL
GROUP BY empresa_id"""

ANSWERS = (
    "taxas cartao credito agrupadas",
    "taxas de cartao por empresa",
    "taxas por bandeira",
    "valor bruto liquido taxa cartao",
    "fechamento gerencial taxas de cartao",
)

VALUE_KEY = "valor_taxa"
TIME_KEY = None
GRAIN = "month"
LABEL_KEY = "empresa_nome"
DEFAULT_MEASURE = "valor_taxa"
DEFAULT_DIMENSION = "empresa_nome"
MEASURES = {
    "valor_bruto": {
        "label": "valor bruto",
        "kind": "money",
        "synonyms": ("bruto", "valor bruto"),
        "additive": True,
    },
    "valor_liquido": {
        "label": "valor liquido",
        "kind": "money",
        "synonyms": ("liquido", "valor liquido"),
        "additive": True,
    },
    "valor_taxa": {
        "label": "valor da taxa",
        "kind": "money",
        "synonyms": ("taxa", "valor taxa", "taxas", "custo da taxa"),
        "additive": True,
    },
    "avg_taxa": {
        "label": "taxa media",
        "kind": "percent",
        "synonyms": ("taxa media", "media da taxa", "avg taxa"),
        "additive": False,
    },
    "quantidade_registros": {
        "label": "quantidade de registros",
        "kind": "count",
        "synonyms": ("quantidade", "registros"),
        "additive": True,
    },
}
DIMENSIONS = {
    "empresa_nome": {"label": "empresa", "synonyms": ("empresa", "empresa faturamento", "empresa_nome")},
    "bandeira": {"label": "bandeira", "synonyms": ("bandeira", "bandeira cartao")},
}
SUPPORTED_OPERATIONS = ("ranking_desc", "ranking_asc", "top_and_bottom", "list")
PARAMETERS = ("date_from", "date_to")
