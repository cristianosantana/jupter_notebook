"""Catálogo de análises SQL (ficheiros em query_sql/). Mesma fonte para recursos MCP e execução."""

from __future__ import annotations

from pathlib import Path
from typing import Final

QUERY_DIR: Final[Path] = Path(__file__).resolve().parent / "query_sql"

QUERY_REGISTRY: dict[str, dict[str, str]] = {
    "cross_selling": {
        "filename": "cross_selling.sql",
        "resource_description": "Pares de serviços na mesma OS; ranking por concessionária e mês.",
        "when_to_use": (
            "Combo de serviços vendidos juntos, cross-sell, frequência de pares na mesma ordem de serviço."
        ),
    },
    "taxa_retrabalho_servico_produtivo_concessionaria": {
        "filename": "taxa_retrabalho_servico_produtivo_concessionaria.sql",
        "resource_description": "Retrabalho vs serviço produtivo por concessionária e período.",
        "when_to_use": (
            "Retrabalho, OS repetidas, qualidade operacional, taxa de retrabalho por unidade."
        ),
    },
    "taxa_conversao_servico_concessionaria_vendedor": {
        "filename": "taxa_conversao_servico_concessionaria_vendedor.sql",
        "resource_description": "Conversão de serviço por concessionária e vendedor.",
        "when_to_use": (
            "Taxa de conversão de proposta/orçamento em venda de serviço, desempenho do vendedor."
        ),
    },
    "servicos_vendidos_por_concessionaria": {
        "filename": "servicos_vendidos_por_concessionaria.sql",
        "resource_description": "Mix de serviços vendidos e share percentual por concessionária e mês.",
        "when_to_use": (
            "Quais serviços mais vendidos, participação no faturamento por linha, mix por unidade."
        ),
    },
    "sazonalidade_por_concessionaria": {
        "filename": "sazonalidade_por_concessionaria.sql",
        "resource_description": "Padrão sazonal de volume/OS por concessionária.",
        "when_to_use": (
            "Sazonalidade, meses mais fortes, variação ao longo do ano por concessionária."
        ),
    },
    "performance_vendedor_periodo": {
        "filename": "performance_vendedor_periodo.sql",
        "resource_description": "KPIs de vendedor: OS, faturamento, ticket, desconto, serviços por OS.",
        "when_to_use": (
            "Ranking de vendedores, ticket médio, desconto médio, produtividade por período."
        ),
    },
    "faturamento_ticket_concessionaria_periodo": {
        "filename": "faturamento_ticket_concessionaria_periodo.sql",
        "resource_description": "Faturamento de serviços, qtd OS e ticket médio por concessionária e mês.",
        "when_to_use": (
            "Faturamento mão de obra/serviços, ticket médio por OS, volume por unidade num intervalo de datas."
        ),
        "params_note": "Obrigatório na tool: date_from e date_to (YYYY-MM-DD).",
    },
    "distribuicao_ticket_percentil": {
        "filename": "distribuicao_ticket_percentil.sql",
        "resource_description": "Distribuição de ticket por quartis (NTILE) por concessionária.",
        "when_to_use": (
            "Segmentação por tamanho de ticket, quartis, perfil premium vs baixo ticket."
        ),
    },
    "propenso_compra_hora_dia_servico": {
        "filename": "propenso_compra_hora_dia_servico.sql",
        "resource_description": "Propensão de compra por hora, dia da semana e tipo de serviço.",
        "when_to_use": (
            "Melhor hora/dia para vender, padrão temporal de compra por serviço."
        ),
    },
}

QUERY_IDS: tuple[str, ...] = tuple(QUERY_REGISTRY.keys())

QUERY_ID_PARAM_HELP = (
    "Identificador da análise. Escolha conforme a intenção:\n"
    + "\n".join(
        f"- {qid}: {QUERY_REGISTRY[qid]['when_to_use']}"
        + (
            f" (Parâmetros: {QUERY_REGISTRY[qid]['params_note']})"
            if QUERY_REGISTRY[qid].get("params_note")
            else ""
        )
        for qid in QUERY_IDS
    )
    + "\n\nNa tool run_analytics_query use date_from/date_to quando a linha acima indicar parâmetros."
)


def get_sql(query_id: str) -> str:
    if query_id not in QUERY_REGISTRY:
        raise KeyError(f"query_id desconhecido: {query_id}")
    meta = QUERY_REGISTRY[query_id]
    path = QUERY_DIR / meta["filename"]
    raw = path.read_text(encoding="utf-8").strip()
    core = raw.rstrip(";").strip()
    if ";" in core:
        raise ValueError("SQL com múltiplas statements não é permitido")
    return core


def format_catalog_for_model() -> str:
    lines = [
        "Catálogo de análises (use o query_id em run_analytics_query). "
        "SQL completo: recurso MCP analytics://query/{query_id}.",
        "",
    ]
    for qid in QUERY_IDS:
        meta = QUERY_REGISTRY[qid]
        lines.append(f"## {qid}")
        lines.append(f"- Quando usar: {meta['when_to_use']}")
        if meta.get("params_note"):
            lines.append(f"- Parâmetros: {meta['params_note']}")
        lines.append(f"- Recurso: analytics://query/{qid}")
        lines.append("")
    return "\n".join(lines).rstrip()
