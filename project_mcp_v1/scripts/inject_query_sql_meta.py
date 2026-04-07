#!/usr/bin/env python3
"""Uso único: injeta cabeçalhos @mcp_query_meta nos .sql (idempotente se já existir)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_QUERY_DIR = _ROOT / "mcp_server" / "query_sql"
_META_TAG = "/* @mcp_query_meta"


def _dq(s: str) -> str:
    return json.dumps(s, ensure_ascii=False)


def _when_block(s: str) -> str:
    body = "\n".join("  " + line for line in s.split("\n"))
    return f"when_to_use: |\n{body}"


def _build_header(
    resource_description: str,
    when_to_use: str,
    output_shape: str,
    not_confused_with: list[str] | None = None,
) -> str:
    lines = [
        "/* @mcp_query_meta",
        f"resource_description: {_dq(resource_description)}",
        _when_block(when_to_use),
        f"output_shape: {output_shape}",
    ]
    if not_confused_with:
        lines.append("not_confused_with:")
        for q in not_confused_with:
            lines.append(f"  - {q}")
    lines.append("@mcp_query_meta */")
    return "\n".join(lines) + "\n\n"


# Conteúdo migrado do QUERY_REGISTRY antigo + output_shape + not_confused_with onde faz sentido
ENTRIES: dict[str, tuple[str, str, str, list[str] | None]] = {
    "cross_selling": (
        "Pares de serviços na mesma OS; ranking por concessionária e mês.",
        "Combo de serviços vendidos juntos, cross-sell, frequência de pares na mesma ordem de serviço.",
        "tabular_multiline",
        None,
    ),
    "taxa_retrabalho_servico_produtivo_concessionaria": (
        "Retrabalho vs serviço produtivo por concessionária e período.",
        "Retrabalho, OS repetidas, qualidade operacional, taxa de retrabalho por unidade.",
        "tabular_multiline",
        None,
    ),
    "taxa_conversao_servico_concessionaria_vendedor": (
        "Conversão de serviço por concessionária e vendedor.",
        "Taxa de conversão de proposta/orçamento em venda de serviço, desempenho do vendedor.",
        "tabular_multiline",
        None,
    ),
    "servicos_vendidos_por_concessionaria": (
        "Mix de serviços vendidos e share percentual por concessionária e mês.",
        "Quais serviços mais vendidos, participação no faturamento por linha, mix por unidade.",
        "tabular_multiline",
        None,
    ),
    "sazonalidade_por_concessionaria": (
        "Padrão sazonal de volume/OS por concessionária.",
        "Sazonalidade, meses mais fortes, variação ao longo do ano por concessionária.",
        "tabular_multiline",
        None,
    ),
    "performance_vendedor_mes": (
        "KPIs de vendedor por concessionária e mês (coluna periodo = YYYY-MM): OS, faturamento, ticket, desconto, serviços por OS.",
        "Ranking de vendedores por mês, ticket médio, desconto médio, produtividade mensal por unidade. "
        "Para totais por ano civil no intervalo de datas, usar performance_vendedor_ano.",
        "tabular_multiline",
        None,
    ),
    "performance_vendedor_ano": (
        "KPIs de vendedor por concessionária e ano civil (coluna periodo_ano = YYYY): mesmas métricas que a análise mensal, agregadas por ano.",
        "Ranking anual de vendedores, faturamento/ticket/desconto agregados por ano no intervalo date_from–date_to "
        "(útil quando o período é um ano completo ou vários anos).",
        "tabular_multiline",
        None,
    ),
    "faturamento_ticket_concessionaria_periodo": (
        "Faturamento de serviços, qtd OS e ticket médio por concessionária e mês.",
        "Faturamento mão de obra/serviços, ticket médio por OS, volume por unidade num intervalo de datas.",
        "tabular_multiline",
        [
            "faturamento_mensal_recebidos_pendentes",
            "faturamento_mensal_recebidos_pendentes_por_concessionaria",
        ],
    ),
    "faturamento_mensal_recebidos_pendentes": (
        "Por mês de competência (YYYY-MM): OS distintas, total recebido (caixas), total pendente "
        "(promessas sem caixa) e faturamento total previsto (recebido + pendente), a partir de caixas/caixas_pendentes.",
        "Lista detalhada do que consegue responder ao interpretar o resultado desta query. "
        "1) Visão geral de faturamento (macro): quanto a empresa produziu/vendeu num mês "
        "(coluna «Faturamento Total Previsto» — serviços da competência, pago na hora + a receber); "
        "evolução vs meses anteriores (uma linha por mês, do mais recente ao mais antigo). "
        "2) Inadimplência e recebíveis: quanto já entrou no caixa (Total Recebido) vs. "
        "valor ainda na rua — promessas não quitadas (Total Pendente); leitura da proporção pendente "
        "face ao faturamento. "
        "3) Volume operacional: quantas OS únicas geraram cobrança no mês (sem duplicar por pagamentos parciais). "
        "KPIs derivados (conta ou Excel): ticket médio mensal = Faturamento Total Previsto ÷ Qtd. OS; "
        "taxa de conversão de recebimento = (Total Recebido ÷ Faturamento Total Previsto) × 100; "
        "taxa de pendência/inadimplência = (Total Pendente ÷ Faturamento Total Previsto) × 100.",
        "tabular_multiline",
        [
            "faturamento_ticket_concessionaria_periodo",
            "faturamento_mensal_recebidos_pendentes_por_concessionaria",
        ],
    ),
    "faturamento_mensal_recebidos_pendentes_por_concessionaria": (
        "Por mês de competência (YYYY-MM) e concessionária: OS distintas, total recebido, total pendente "
        "e faturamento previsto (caixas + caixas_pendentes via os).",
        "Mesma lógica que faturamento_mensal_recebidos_pendentes, mas com GROUP BY por concessionária. "
        "Curva ABC por unidade (quem mais fatura por mês; ORDER BY faturamento total DESC). "
        "Risco de inadimplência por cliente: comparar Total Pendente vs Faturamento Total Previsto por loja. "
        "Volume operacional: Qtd. OS vs faturamento entre concessionárias (eficiência relativa). "
        "Use faturamento_mensal_recebidos_pendentes quando precisar só do agregado mensal global (sem quebra por loja).",
        "tabular_multiline",
        [
            "faturamento_ticket_concessionaria_periodo",
            "faturamento_mensal_recebidos_pendentes",
        ],
    ),
    "distribuicao_ticket_percentil": (
        "Distribuição de ticket por quartis (NTILE) por concessionária.",
        "Segmentação por tamanho de ticket, quartis, perfil premium vs baixo ticket.",
        "tabular_multiline",
        None,
    ),
    "propenso_compra_hora_dia_servico": (
        "Propensão de compra por hora, dia da semana e tipo de serviço.",
        "Melhor hora/dia para vender, padrão temporal de compra por serviço.",
        "tabular_multiline",
        None,
    ),
    "volume_os_concessionaria_mom": (
        "Volume de OS por concessionária com variação MoM (JSON agregado).",
        "Volume mensal de OS, abertas/fechadas/canceladas, taxa de cancelamento e variação mês a mês.",
        "json_aggregate",
        None,
    ),
    "volume_os_vendedor_ranking": (
        "Volume de OS por vendedor e concessionária com ranking (JSON).",
        "Ranking de vendedores por quantidade de OS, fechamentos e taxa de fechamento.",
        "json_aggregate",
        None,
    ),
    "ticket_medio_concessionaria_agg": (
        "Ticket médio e dispersão por concessionária (JSON).",
        "Ticket médio, mín/máx, desvio padrão e faturamento por concessionária em OS fechadas.",
        "json_aggregate",
        None,
    ),
    "ticket_medio_vendedor_top_bottom": (
        "Top 5 e bottom 5 vendedores por ticket médio (JSON).",
        "Destaques e caudas de desempenho por ticket médio por vendedor.",
        "json_aggregate",
        None,
    ),
    "taxa_conversao_servicos_os_fechada": (
        "Conversão de linhas de serviço em OS fechadas, global e por loja (JSON).",
        "Quantidade de serviços (itens) vs OS fechadas; taxa global e por concessionária.",
        "json_aggregate",
        None,
    ),
}


def main() -> int:
    missing = []
    for stem, tup in ENTRIES.items():
        p = _QUERY_DIR / f"{stem}.sql"
        if not p.is_file():
            missing.append(stem)
    if missing:
        print("Ficheiros em falta:", missing, file=sys.stderr)
        return 1

    for stem, (rd, wtu, shape, ncf) in ENTRIES.items():
        p = _QUERY_DIR / f"{stem}.sql"
        raw = p.read_text(encoding="utf-8")
        if _META_TAG in raw:
            print("skip (já tem meta):", stem)
            continue
        hdr = _build_header(rd, wtu, shape, ncf)
        p.write_text(hdr + raw, encoding="utf-8")
        print("ok:", stem)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
