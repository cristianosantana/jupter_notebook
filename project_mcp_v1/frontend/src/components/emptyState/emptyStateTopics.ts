export type EmptyStateTopic = {
  id: string
  /** Título curto no card (estilo “chip” / Gemini). */
  title: string
  icon: string
  /** Texto completo enviado ao assistente ao clicar. */
  text: string
}

/** Sugestões alinhadas ao catálogo de analytics (`when_to_use` / domínio do assistente). */
export const EMPTY_STATE_TOPICS: EmptyStateTopic[] = [
  {
    id: 'servicos-mix',
    icon: '🧩',
    title: 'Mix de serviços',
    text: 'Quais serviços mais vendidos, participação no faturamento por linha, mix por unidade.',
  },
  {
    id: 'sazonalidade',
    icon: '📅',
    title: 'Sazonalidade',
    text: 'Sazonalidade, meses mais fortes, variação ao longo do ano por concessionária.',
  },
  {
    id: 'performance-vendedor-mes',
    icon: '👤',
    title: 'Vendedores por mês',
    text: 'Ranking de vendedores por mês, ticket médio, desconto médio, produtividade mensal por unidade.',
  },
  {
    id: 'performance-vendedor-ano',
    icon: '🏆',
    title: 'Vendedores no ano',
    text: 'Ranking anual de vendedores, faturamento/ticket/desconto agregados por ano no intervalo date_from–date_to.',
  },
  {
    id: 'faturamento-ticket-periodo',
    icon: '💶',
    title: 'Faturamento e ticket',
    text: 'Faturamento mão de obra/serviços, ticket médio por OS, volume por unidade num intervalo de datas.',
  },
  {
    id: 'distribuicao-ticket',
    icon: '📊',
    title: 'Distribuição de tickets',
    text: 'Segmentação por tamanho de ticket, quartis, perfil premium vs baixo ticket.',
  },
  {
    id: 'propensao-temporal',
    icon: '⏰',
    title: 'Melhor hora para vender',
    text: 'Melhor hora/dia para vender, padrão temporal de compra por serviço.',
  },
  {
    id: 'volume-os-mom',
    icon: '📆',
    title: 'Volume mensal de OS',
    text: 'Volume mensal de OS, abertas/fechadas/canceladas, taxa de cancelamento e variação mês a mês.',
  },
  {
    id: 'volume-os-vendedor',
    icon: '📋',
    title: 'OS por vendedor',
    text: 'Ranking de vendedores por quantidade de OS, fechamentos e taxa de fechamento.',
  },
  {
    id: 'ticket-concessionaria',
    icon: '🏪',
    title: 'Ticket por concessionária',
    text: 'Ticket médio, mín/máx, desvio padrão e faturamento por concessionária em OS fechadas.',
  },
  {
    id: 'ticket-vendedor-top-bottom',
    icon: '⬆️',
    title: 'Top e cauda (ticket)',
    text: 'Destaques e caudas de desempenho por ticket médio por vendedor.',
  },
  {
    id: 'conversao-servicos-os',
    icon: '🔗',
    title: 'Serviços → OS fechadas',
    text: 'Quantidade de serviços (itens) vs OS fechadas; taxa global e por concessionária.',
  },
  {
    id: 'faturamento-mensal-macro',
    icon: '📈',
    title: 'Faturamento macro (mês)',
    text:
      '1) Visão geral de faturamento (macro): quanto a empresa produziu/vendeu num mês ' +
      '(coluna «Faturamento Total Previsto» — serviços da competência, pago na hora + a receber); ' +
      'evolução vs meses anteriores (uma linha por mês, do mais recente ao mais antigo).',
  },
  {
    id: 'faturamento-mensal-recebiveis',
    icon: '💳',
    title: 'Recebidos vs pendentes',
    text:
      '2) Inadimplência e recebíveis: quanto já entrou no caixa (Total Recebido) vs. ' +
      'valor ainda na rua — promessas não quitadas (Total Pendente); leitura da proporção pendente ' +
      'face ao faturamento.',
  },
  {
    id: 'faturamento-mensal-kpis',
    icon: '📐',
    title: 'KPIs mensais (OS / taxas)',
    text:
      '3) Volume operacional: quantas OS únicas geraram cobrança no mês (sem duplicar por pagamentos parciais). ' +
      'KPIs derivados (conta ou Excel): ticket médio mensal = Faturamento Total Previsto ÷ Qtd. OS; ' +
      'taxa de conversão de recebimento = (Total Recebido ÷ Faturamento Total Previsto) × 100; ' +
      'taxa de pendência/inadimplência = (Total Pendente ÷ Faturamento Total Previsto) × 100.',
  },
  {
    id: 'faturamento-mensal-recebidos-pendentes-por-concessionaria',
    icon: '🗺️',
    title: 'Faturamento por loja',
    text:
      'Mesma lógica que faturamento_mensal_recebidos_pendentes, mas com GROUP BY por concessionária. ' +
      'Curva ABC por unidade (quem mais fatura por mês; ORDER BY faturamento total DESC). ' +
      'Risco de inadimplência por cliente: comparar Total Pendente vs Faturamento Total Previsto por loja. ' +
      'Volume operacional: Qtd. OS vs faturamento entre concessionárias (eficiência relativa). ' +
      'Use faturamento_mensal_recebidos_pendentes quando precisar só do agregado mensal global (sem quebra por loja).',
  },
  {
    id: 'curva-abc-por-concessionaria',
    icon: '🔤',
    title: 'Curva ABC por unidade',
    text: 'Curva ABC por unidade (quem mais fatura por mês; ORDER BY faturamento total DESC). ',
  },
  {
    id: 'risco-inadimplencia-por-concessionaria',
    icon: '⚠️',
    title: 'Risco de inadimplência',
    text: 'Risco de inadimplência por cliente: comparar Total Pendente vs Faturamento Total Previsto por loja. ',
  },
  {
    id: 'volume-operacional-por-concessionaria',
    icon: '⚙️',
    title: 'Volume operacional',
    text: 'Volume operacional: Qtd. OS vs faturamento entre concessionárias (eficiência relativa). ',
  },
  {
    id: 'use-faturamento-mensal-recebidos-pendentes',
    icon: '🌐',
    title: 'Agregado global (mês)',
    text: 'Use faturamento_mensal_recebidos_pendentes quando precisar só do agregado mensal global (sem quebra por loja).',
  },
]

export function topicCardPreview(text: string, maxLen = 110): string {
  const t = text.trim()
  if (t.length <= maxLen) return t
  return `${t.slice(0, maxLen - 1).trim()}…`
}
