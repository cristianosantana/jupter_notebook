"""Sugestões do estado vazio (espelho de EMPTY_STATE_TOPICS no App.tsx)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EmptyStateTopic:
    id: str
    title: str
    icon: str
    text: str


EMPTY_STATE_TOPICS: tuple[EmptyStateTopic, ...] = (
    EmptyStateTopic(
        id="servicos-mix",
        icon="🧩",
        title="Mix de serviços",
        text="Quais serviços mais vendidos, participação no faturamento por linha, mix por unidade.",
    ),
    EmptyStateTopic(
        id="sazonalidade",
        icon="📅",
        title="Sazonalidade",
        text="Sazonalidade, meses mais fortes, variação ao longo do ano por concessionária.",
    ),
    EmptyStateTopic(
        id="performance-vendedor-mes",
        icon="👤",
        title="Vendedores por mês",
        text="Ranking de vendedores por mês, ticket médio, desconto médio, produtividade mensal por unidade.",
    ),
    EmptyStateTopic(
        id="performance-vendedor-ano",
        icon="🏆",
        title="Vendedores no ano",
        text="Ranking anual de vendedores, faturamento/ticket/desconto agregados por ano no intervalo date_from–date_to.",
    ),
    EmptyStateTopic(
        id="faturamento-ticket-periodo",
        icon="💶",
        title="Faturamento e ticket",
        text="Faturamento mão de obra/serviços, ticket médio por OS, volume por unidade num intervalo de datas.",
    ),
    EmptyStateTopic(
        id="distribuicao-ticket",
        icon="📊",
        title="Distribuição de tickets",
        text="Segmentação por tamanho de ticket, quartis, perfil premium vs baixo ticket.",
    ),
    EmptyStateTopic(
        id="propensao-temporal",
        icon="⏰",
        title="Melhor hora para vender",
        text="Melhor hora/dia para vender, padrão temporal de compra por serviço.",
    ),
    EmptyStateTopic(
        id="volume-os-mom",
        icon="📆",
        title="Volume mensal de OS",
        text="Volume mensal de OS, abertas/fechadas/canceladas, taxa de cancelamento e variação mês a mês.",
    ),
    EmptyStateTopic(
        id="volume-os-vendedor",
        icon="📋",
        title="OS por vendedor",
        text="Ranking de vendedores por quantidade de OS, fechamentos e taxa de fechamento.",
    ),
    EmptyStateTopic(
        id="ticket-concessionaria",
        icon="🏪",
        title="Ticket por concessionária",
        text="Ticket médio, mín/máx, desvio padrão e faturamento por concessionária em OS fechadas.",
    ),
    EmptyStateTopic(
        id="ticket-vendedor-top-bottom",
        icon="⬆️",
        title="Top e cauda (ticket)",
        text="Destaques e caudas de desempenho por ticket médio por vendedor.",
    ),
    EmptyStateTopic(
        id="conversao-servicos-os",
        icon="🔗",
        title="Serviços → OS fechadas",
        text="Quantidade de serviços (itens) vs OS fechadas; taxa global e por concessionária.",
    ),
    EmptyStateTopic(
        id="faturamento-mensal-macro",
        icon="📈",
        title="Faturamento macro (mês)",
        text=(
            "1) Visão geral de faturamento (macro): quanto a empresa produziu/vendeu num mês "
            "(coluna «Faturamento Total Previsto» — serviços da competência, pago na hora + a receber); "
            "evolução vs meses anteriores (uma linha por mês, do mais recente ao mais antigo)."
        ),
    ),
    EmptyStateTopic(
        id="faturamento-mensal-recebiveis",
        icon="💳",
        title="Recebidos vs pendentes",
        text=(
            "2) Inadimplência e recebíveis: quanto já entrou no caixa (Total Recebido) vs. "
            "valor ainda na rua — promessas não quitadas (Total Pendente); leitura da proporção pendente "
            "face ao faturamento."
        ),
    ),
    EmptyStateTopic(
        id="faturamento-mensal-kpis",
        icon="📐",
        title="KPIs mensais (OS / taxas)",
        text=(
            "3) Volume operacional: quantas OS únicas geraram cobrança no mês (sem duplicar por pagamentos parciais). "
            "KPIs derivados (conta ou Excel): ticket médio mensal = Faturamento Total Previsto ÷ Qtd. OS; "
            "taxa de conversão de recebimento = (Total Recebido ÷ Faturamento Total Previsto) × 100; "
            "taxa de pendência/inadimplência = (Total Pendente ÷ Faturamento Total Previsto) × 100."
        ),
    ),
    EmptyStateTopic(
        id="faturamento-mensal-recebidos-pendentes-por-concessionaria",
        icon="🗺️",
        title="Faturamento por loja",
        text=(
            "Mesma lógica que faturamento_mensal_recebidos_pendentes, mas com GROUP BY por concessionária. "
            "Curva ABC por unidade (quem mais fatura por mês; ORDER BY faturamento total DESC). "
            "Risco de inadimplência por cliente: comparar Total Pendente vs Faturamento Total Previsto por loja. "
            "Volume operacional: Qtd. OS vs faturamento entre concessionárias (eficiência relativa). "
            "Use faturamento_mensal_recebidos_pendentes quando precisar só do agregado mensal global (sem quebra por loja)."
        ),
    ),
    EmptyStateTopic(
        id="curva-abc-por-concessionaria",
        icon="🔤",
        title="Curva ABC por unidade",
        text="Curva ABC por unidade (quem mais fatura por mês; ORDER BY faturamento total DESC). ",
    ),
    EmptyStateTopic(
        id="risco-inadimplencia-por-concessionaria",
        icon="⚠️",
        title="Risco de inadimplência",
        text="Risco de inadimplência por cliente: comparar Total Pendente vs Faturamento Total Previsto por loja. ",
    ),
    EmptyStateTopic(
        id="volume-operacional-por-concessionaria",
        icon="⚙️",
        title="Volume operacional",
        text="Volume operacional: Qtd. OS vs faturamento entre concessionárias (eficiência relativa). ",
    ),
    EmptyStateTopic(
        id="use-faturamento-mensal-recebidos-pendentes",
        icon="🌐",
        title="Agregado global (mês)",
        text="Use faturamento_mensal_recebidos_pendentes quando precisar só do agregado mensal global (sem quebra por loja).",
    ),
)


def topic_card_preview(text: str, max_len: int = 110) -> str:
    t = text.strip()
    if len(t) <= max_len:
        return t
    return f"{t[: max_len - 1].strip()}…"
