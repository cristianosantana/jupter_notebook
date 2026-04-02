"""Catálogo de análises SQL (ficheiros em query_sql/). Mesma fonte para recursos MCP e execução."""

from __future__ import annotations

from pathlib import Path
from typing import Final

QUERY_DIR: Final[Path] = Path(__file__).resolve().parent / "query_sql"

# query_id com resultado tabular multi-linha (várias linhas por execução). Só para o catálogo em
# format_catalog_for_model; run_analytics_query usa summarize=true/false para compacto vs rows completos.
TABULAR_MULTIROW_QUERY_IDS: Final[frozenset[str]] = frozenset(
    {
        "cross_selling",
        "taxa_retrabalho_servico_produtivo_concessionaria",
        "taxa_conversao_servico_concessionaria_vendedor",
        "servicos_vendidos_por_concessionaria",
        "sazonalidade_por_concessionaria",
        "performance_vendedor_mes",
        "performance_vendedor_ano",
        "faturamento_ticket_concessionaria_periodo",
        "faturamento_mensal_recebidos_pendentes",
        "faturamento_mensal_recebidos_pendentes_por_concessionaria",
        "distribuicao_ticket_percentil",
        "propenso_compra_hora_dia_servico",
    }
)

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
    "performance_vendedor_mes": {
        "filename": "performance_vendedor_mes.sql",
        "resource_description": (
            "KPIs de vendedor por concessionária e mês (coluna periodo = YYYY-MM): OS, faturamento, ticket, desconto, serviços por OS."
        ),
        "when_to_use": (
            "Ranking de vendedores por mês, ticket médio, desconto médio, produtividade mensal por unidade. "
            "Para totais por ano civil no intervalo de datas, usar performance_vendedor_ano."
        ),
    },
    "performance_vendedor_ano": {
        "filename": "performance_vendedor_ano.sql",
        "resource_description": (
            "KPIs de vendedor por concessionária e ano civil (coluna periodo_ano = YYYY): mesmas métricas que a análise mensal, agregadas por ano."
        ),
        "when_to_use": (
            "Ranking anual de vendedores, faturamento/ticket/desconto agregados por ano no intervalo date_from–date_to "
            "(útil quando o período é um ano completo ou vários anos)."
        ),
    },
    "faturamento_ticket_concessionaria_periodo": {
        "filename": "faturamento_ticket_concessionaria_periodo.sql",
        "resource_description": "Faturamento de serviços, qtd OS e ticket médio por concessionária e mês.",
        "when_to_use": (
            "Faturamento mão de obra/serviços, ticket médio por OS, volume por unidade num intervalo de datas."
        ),
    },
    "faturamento_mensal_recebidos_pendentes": {
        "filename": "faturamento_mensal_recebidos_pendentes.sql",
        "resource_description": (
            "Por mês de competência (YYYY-MM): OS distintas, total recebido (caixas), total pendente "
            "(promessas sem caixa) e faturamento total previsto (recebido + pendente), a partir de caixas/caixas_pendentes."
        ),
        "when_to_use": (
            "Lista detalhada do que consegue responder ao interpretar o resultado desta query. "
            "1) Visão geral de faturamento (macro): quanto a empresa produziu/vendeu num mês "
            '(coluna «Faturamento Total Previsto» — serviços da competência, pago na hora + a receber); '
            "evolução vs meses anteriores (uma linha por mês, do mais recente ao mais antigo). "
            "2) Inadimplência e recebíveis: quanto já entrou no caixa (Total Recebido) vs. "
            "valor ainda na rua — promessas não quitadas (Total Pendente); leitura da proporção pendente "
            "face ao faturamento. "
            "3) Volume operacional: quantas OS únicas geraram cobrança no mês (sem duplicar por pagamentos parciais). "
            "KPIs derivados (conta ou Excel): ticket médio mensal = Faturamento Total Previsto ÷ Qtd. OS; "
            "taxa de conversão de recebimento = (Total Recebido ÷ Faturamento Total Previsto) × 100; "
            "taxa de pendência/inadimplência = (Total Pendente ÷ Faturamento Total Previsto) × 100."
        ),
    },
    "faturamento_mensal_recebidos_pendentes_por_concessionaria": {
        "filename": "faturamento_mensal_recebidos_pendentes_por_concessionaria.sql",
        "resource_description": (
            "Por mês de competência (YYYY-MM) e concessionária: OS distintas, total recebido, total pendente "
            "e faturamento previsto (caixas + caixas_pendentes via os)."
        ),
        "when_to_use": (
            "Mesma lógica que faturamento_mensal_recebidos_pendentes, mas com GROUP BY por concessionária. "
            "Curva ABC por unidade (quem mais fatura por mês; ORDER BY faturamento total DESC). "
            "Risco de inadimplência por cliente: comparar Total Pendente vs Faturamento Total Previsto por loja. "
            "Volume operacional: Qtd. OS vs faturamento entre concessionárias (eficiência relativa). "
            "Use faturamento_mensal_recebidos_pendentes quando precisar só do agregado mensal global (sem quebra por loja)."
        ),
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
    "volume_os_concessionaria_mom": {
        "filename": "volume_os_concessionaria_mom.sql",
        "resource_description": "Volume de OS por concessionária com variação MoM (JSON agregado).",
        "when_to_use": (
            "Volume mensal de OS, abertas/fechadas/canceladas, taxa de cancelamento e variação mês a mês."
        ),
    },
    "volume_os_vendedor_ranking": {
        "filename": "volume_os_vendedor_ranking.sql",
        "resource_description": "Volume de OS por vendedor e concessionária com ranking (JSON).",
        "when_to_use": (
            "Ranking de vendedores por quantidade de OS, fechamentos e taxa de fechamento."
        ),
    },
    "ticket_medio_concessionaria_agg": {
        "filename": "ticket_medio_concessionaria_agg.sql",
        "resource_description": "Ticket médio e dispersão por concessionária (JSON).",
        "when_to_use": (
            "Ticket médio, mín/máx, desvio padrão e faturamento por concessionária em OS fechadas."
        ),
    },
    "ticket_medio_vendedor_top_bottom": {
        "filename": "ticket_medio_vendedor_top_bottom.sql",
        "resource_description": "Top 5 e bottom 5 vendedores por ticket médio (JSON).",
        "when_to_use": (
            "Destaques e caudas de desempenho por ticket médio por vendedor."
        ),
    },
    "taxa_conversao_servicos_os_fechada": {
        "filename": "taxa_conversao_servicos_os_fechada.sql",
        "resource_description": "Conversão de linhas de serviço em OS fechadas, global e por loja (JSON).",
        "when_to_use": (
            "Quantidade de serviços (itens) vs OS fechadas; taxa global e por concessionária."
        ),
    },
}

# Contexto inicial: domínio que o agente cobre para responder (catálogo + MCP + instruções ao modelo).
AGENT_ANALYTICS_DOMAIN_INTRO: Final[str] = (
    "Domínio do agente: análises sobre oficina/concessionária em MySQL — ordens de serviço (OS), "
    "serviços e linhas vendidas, faturamento e ticket, vendedores e concessionárias, descontos, "
    "volume e estado das OS (abertas/fechadas/canceladas), sazonalidade, mix de serviços, "
    "retrabalho, conversão de serviço/OS, cross-selling, faturamento mensal recebido vs pendente (caixas, global e por concessionária), "
    "distribuição de tickets (percentis) e "
    "propensão de compra por hora/dia. Só responde com base nas análises SQL catalogadas neste "
    "ficheiro (query_id); período sempre delimitado por date_from e date_to (YYYY-MM-DD). "
    "Fora deste catálogo não há execução automática de relatórios ad-hoc."
)

QUERY_IDS: tuple[str, ...] = tuple(QUERY_REGISTRY.keys())

# Todas as queries em query_sql/ usam __MCP_DATE_FROM__ / __MCP_DATE_TO__ no SQL (visíveis no recurso MCP).
GLOBAL_PERIOD_HELP = (
    "Todas as análises filtram por intervalo de datas: em run_analytics_query são obrigatórios "
    "date_from e date_to (YYYY-MM-DD). O recurso MCP analytics://query/{query_id} mostra o SQL com "
    "os placeholders __MCP_DATE_FROM__ e __MCP_DATE_TO__. "
    "Para qualquer query_id: com summarize=false o JSON inclui o campo rows com todas as linhas retornadas "
    "nesta página (até limit; usar offset para paginar). Com summarize=true a resposta é compacta "
    "(rows_sample e opcionalmente llm_summary via sampling MCP)."
)

QUERY_ID_PARAM_HELP = (
    AGENT_ANALYTICS_DOMAIN_INTRO
    + "\n\n"
    + GLOBAL_PERIOD_HELP
    + "\n\nIdentificador da análise. Escolha conforme a intenção:\n"
    + "\n".join(
        f"- {qid}: {QUERY_REGISTRY[qid]['when_to_use']}"
        for qid in QUERY_IDS
    )
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
        AGENT_ANALYTICS_DOMAIN_INTRO,
        "",
        "Catálogo de análises (use o query_id em run_analytics_query). "
        "SQL completo: recurso MCP analytics://query/{query_id}.",
        "",
        GLOBAL_PERIOD_HELP,
        "",
    ]
    for qid in QUERY_IDS:
        meta = QUERY_REGISTRY[qid]
        lines.append(f"## {qid}")
        if qid in TABULAR_MULTIROW_QUERY_IDS:
            lines.append(
                "- Formato: tabular multi-linha no SQL; summarize=false devolve o campo rows com todas as linhas "
                "da página (até limit); summarize=true devolve formato compacto (rows_sample / resumo)."
            )
        else:
            lines.append(
                "- Formato: uma linha típica com coluna `resultado` (JSON agregado no MySQL)."
            )
        lines.append(f"- Quando usar: {meta['when_to_use']}")
        lines.append(f"- Recurso: analytics://query/{qid}")
        lines.append("")
    return "\n".join(lines).rstrip()
