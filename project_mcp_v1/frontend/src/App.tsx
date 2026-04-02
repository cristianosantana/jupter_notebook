import { useCallback, useEffect, useRef, useState } from 'react'
import type { ReactNode, SubmitEvent } from 'react'

type ContentBlock =
  | { type: 'paragraph'; text: string }
  | { type: 'heading'; level?: 1 | 2 | 3; text: string }
  | {
      type: 'table'
      columns: string[]
      rows: (string | number | boolean | null)[][]
    }
  | {
      type: 'metric_grid'
      items: { label: string; value: string }[]
    }

type ContentBlocksPayload = { version: 1; blocks: ContentBlock[] }

type ChatMessage =
  | { role: 'user'; content: string }
  | {
      role: 'assistant'
      content: string
      contentBlocks?: ContentBlocksPayload | null
    }

type SessionRow = {
  session_id: string
  user_id: string | null
  current_agent: string
  status: string
  started_at: string | null
  last_active_at: string | null
}

type ChatResponse = {
  reply: string
  content_blocks?: ContentBlocksPayload | null
  tools_used: unknown[]
  agent_used: string
  trace_run_id?: string | null
  session_id?: string
  user_id?: string
}

type SessionDetailResponse = {
  session: SessionRow & { metadata?: Record<string, unknown> }
  messages: StoredMsg[]
  trace_run_id: string | null
  persistence_enabled?: boolean
}

type StoredMsg = {
  role?: string
  content?: unknown
  name?: string
}

const demoUserId = import.meta.env.VITE_DEMO_USER_ID as string | undefined

/** Etapas fictícias de “pipeline” no servidor — só para reduzir ansiedade à espera. */
const PIPELINE_STEPS = [
  'Consultando base de dados…',
  'Buscando informações relevantes…',
  'Analisando resultados…',
  'Acertando detalhes…',
  'Formando resposta…',
] as const

type EmptyStateTopic = {
  id: string
  text: string
}

/** Sugestões alinhadas ao catálogo de analytics (`when_to_use` / domínio do assistente). */
const EMPTY_STATE_TOPICS: EmptyStateTopic[] = [
  {
    id: 'servicos-mix',
    text: 'Quais serviços mais vendidos, participação no faturamento por linha, mix por unidade.',
  },
  {
    id: 'sazonalidade',
    text: 'Sazonalidade, meses mais fortes, variação ao longo do ano por concessionária.',
  },
  {
    id: 'performance-vendedor-mes',
    text: 'Ranking de vendedores por mês, ticket médio, desconto médio, produtividade mensal por unidade.',
  },
  {
    id: 'performance-vendedor-ano',
    text: 'Ranking anual de vendedores, faturamento/ticket/desconto agregados por ano no intervalo date_from–date_to.',
  },
  {
    id: 'faturamento-ticket-periodo',
    text: 'Faturamento mão de obra/serviços, ticket médio por OS, volume por unidade num intervalo de datas.',
  },
  {
    id: 'distribuicao-ticket',
    text: 'Segmentação por tamanho de ticket, quartis, perfil premium vs baixo ticket.',
  },
  {
    id: 'propensao-temporal',
    text: 'Melhor hora/dia para vender, padrão temporal de compra por serviço.',
  },
  {
    id: 'volume-os-mom',
    text: 'Volume mensal de OS, abertas/fechadas/canceladas, taxa de cancelamento e variação mês a mês.',
  },
  {
    id: 'volume-os-vendedor',
    text: 'Ranking de vendedores por quantidade de OS, fechamentos e taxa de fechamento.',
  },
  {
    id: 'ticket-concessionaria',
    text: 'Ticket médio, mín/máx, desvio padrão e faturamento por concessionária em OS fechadas.',
  },
  {
    id: 'ticket-vendedor-top-bottom',
    text: 'Destaques e caudas de desempenho por ticket médio por vendedor.',
  },
  {
    id: 'conversao-servicos-os',
    text: 'Quantidade de serviços (itens) vs OS fechadas; taxa global e por concessionária.',
  },
  {
    id: 'faturamento-mensal-macro',
    text:
      '1) Visão geral de faturamento (macro): quanto a empresa produziu/vendeu num mês ' +
      '(coluna «Faturamento Total Previsto» — serviços da competência, pago na hora + a receber); ' +
      'evolução vs meses anteriores (uma linha por mês, do mais recente ao mais antigo).',
  },
  {
    id: 'faturamento-mensal-recebiveis',
    text:
      '2) Inadimplência e recebíveis: quanto já entrou no caixa (Total Recebido) vs. ' +
      'valor ainda na rua — promessas não quitadas (Total Pendente); leitura da proporção pendente ' +
      'face ao faturamento.',
  },
  {
    id: 'faturamento-mensal-kpis',
    text:
      '3) Volume operacional: quantas OS únicas geraram cobrança no mês (sem duplicar por pagamentos parciais). ' +
      'KPIs derivados (conta ou Excel): ticket médio mensal = Faturamento Total Previsto ÷ Qtd. OS; ' +
      'taxa de conversão de recebimento = (Total Recebido ÷ Faturamento Total Previsto) × 100; ' +
      'taxa de pendência/inadimplência = (Total Pendente ÷ Faturamento Total Previsto) × 100.',
  },
  {
    id: 'faturamento-mensal-recebidos-pendentes-por-concessionaria',
    text: 'Mesma lógica que faturamento_mensal_recebidos_pendentes, mas com GROUP BY por concessionária. ' +
      'Curva ABC por unidade (quem mais fatura por mês; ORDER BY faturamento total DESC). ' +
      'Risco de inadimplência por cliente: comparar Total Pendente vs Faturamento Total Previsto por loja. ' +
      'Volume operacional: Qtd. OS vs faturamento entre concessionárias (eficiência relativa). ' +
      'Use faturamento_mensal_recebidos_pendentes quando precisar só do agregado mensal global (sem quebra por loja).',
  },
  {
    id: 'curva-abc-por-concessionaria',
    text: 'Curva ABC por unidade (quem mais fatura por mês; ORDER BY faturamento total DESC). ',
  },
  {
    id: 'risco-inadimplencia-por-concessionaria',
    text: 'Risco de inadimplência por cliente: comparar Total Pendente vs Faturamento Total Previsto por loja. ',
  },
  {
    id: 'volume-operacional-por-concessionaria',
    text: 'Volume operacional: Qtd. OS vs faturamento entre concessionárias (eficiência relativa). ',
  },
  {
    id: 'use-faturamento-mensal-recebidos-pendentes',
    text: 'Use faturamento_mensal_recebidos_pendentes quando precisar só do agregado mensal global (sem quebra por loja).',
  },
]

/** Divide uma linha em células por `|` (vazios omitidos). */
function splitPipeCells(line: string): string[] {
  return line.split('|').map((c) => c.trim()).filter((c) => c.length > 0)
}

function countPipes(s: string): number {
  return (s.match(/\|/g) ?? []).length
}

/** Pelo menos dois pipes e duas células não vazias — padrão tipo `| Jun 1 | Jul 2 |`. */
function isPipeDenseLine(s: string): boolean {
  return countPipes(s) >= 2 && splitPipeCells(s).length >= 2
}

/**
 * Separa texto introdutório do primeiro `|` quando o resto continua a ser tabular.
 */
function extractPipeTableFromLine(line: string): {
  caption: string | null
  pipeLine: string
} {
  const trimmed = line.trim()
  if (!isPipeDenseLine(trimmed)) {
    return { caption: null, pipeLine: trimmed }
  }
  const firstPipe = trimmed.indexOf('|')
  const preamble = trimmed.slice(0, firstPipe).trim()
  const rest = trimmed.slice(firstPipe).trim()
  if (!isPipeDenseLine(rest)) {
    return { caption: null, pipeLine: trimmed }
  }
  return {
    caption: preamble.length > 0 ? preamble : null,
    pipeLine: rest,
  }
}

/** Células no formato mês + valor (ex.: `Jun 199.550`, `Oct 200.`, `Jan R$ 1.234,56`). */
const PIPE_CELL_MONTH_VALUE =
  /^([A-Za-zÀ-ú]{3,})\s+(?:R\$\s*)?([\d\s.,]+(?:\s*[%‰])?)$/

function tryMonthValueSemanticTable(
  matrix: string[][],
): { headers: string[]; values: string[] } | null {
  if (matrix.length !== 1) return null
  const cells = matrix[0]
  const headers: string[] = []
  const values: string[] = []
  for (const c of cells) {
    const m = c.trim().match(PIPE_CELL_MONTH_VALUE)
    if (!m) return null
    headers.push(m[1])
    values.push(m[2].trim())
  }
  return headers.length >= 2 ? { headers, values } : null
}

function PipeTableView({ rows }: { rows: string[] }) {
  const matrix = rows.map((r) => splitPipeCells(r))
  if (matrix.length === 0 || matrix.every((r) => r.length === 0)) return null
  const maxCols = Math.max(...matrix.map((r) => r.length), 1)
  const semantic = tryMonthValueSemanticTable(matrix)

  const wrap = (inner: ReactNode) => (
    <div className="my-3 overflow-x-auto rounded-xl border border-slate-200/90 bg-white shadow-sm ring-1 ring-slate-900/[0.03]">
      {inner}
    </div>
  )

  if (semantic) {
    return wrap(
      <table className="min-w-full text-left text-[0.8125rem] text-slate-800">
        <thead>
          <tr className="border-b border-slate-200 bg-slate-50">
            {semantic.headers.map((h, hi) => (
              <th
                key={hi}
                className="whitespace-nowrap px-3 py-2 font-semibold text-slate-700"
              >
                {renderInlineBold(h)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          <tr className="bg-white">
            {semantic.values.map((v, vi) => (
              <td
                key={vi}
                className="border-t border-slate-100 px-3 py-2.5 tabular-nums font-medium text-slate-900"
              >
                {renderInlineBold(v)}
              </td>
            ))}
          </tr>
        </tbody>
      </table>,
    )
  }

  return wrap(
    <table className="min-w-full text-left text-[0.8125rem] text-slate-800">
      <tbody>
        {matrix.map((row, ri) => (
          <tr
            key={ri}
            className="border-b border-slate-100 last:border-0 odd:bg-white even:bg-slate-50/70"
          >
            {Array.from({ length: maxCols }, (_, ci) => (
              <td
                key={ci}
                className="px-3 py-2 align-top text-slate-700 [&:not(:last-child)]:border-r border-slate-100"
              >
                {row[ci] != null && row[ci] !== ''
                  ? renderInlineBold(row[ci])
                  : '—'}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>,
  )
}

/** Realça `**negrito**` estilo Markdown comum nas respostas do modelo. */
function renderInlineBold(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g)
  return parts.map((part, i) => {
    const m = part.match(/^\*\*([^*]+)\*\*$/)
    if (m) {
      return (
        <strong key={i} className="font-semibold text-slate-900">
          {m[1]}
        </strong>
      )
    }
    return <span key={i}>{part}</span>
  })
}

type AssistantChunk =
  | { kind: 'spacer' }
  | { kind: 'heading'; level: 1 | 2 | 3; text: string }
  | { kind: 'numbered'; raw: string }
  | { kind: 'bullets'; items: string[] }
  | { kind: 'paragraph'; lines: string[] }
  | { kind: 'choice'; letter: string; rest: string }
  | { kind: 'pipe_table'; rows: string[]; caption: string | null }

function parseAssistantChunks(lines: string[]): AssistantChunk[] {
  const chunks: AssistantChunk[] = []
  let i = 0
  while (i < lines.length) {
    const trimmed = lines[i].trim()
    if (!trimmed) {
      chunks.push({ kind: 'spacer' })
      i++
      continue
    }
    const mdHeading = trimmed.match(/^(#{1,3})\s+(.+)$/)
    if (mdHeading) {
      const n = mdHeading[1].length as 1 | 2 | 3
      chunks.push({ kind: 'heading', level: n, text: mdHeading[2] })
      i++
      continue
    }
    if (/^(?:\d+\)|\d+\.\s)/.test(trimmed)) {
      chunks.push({ kind: 'numbered', raw: trimmed })
      i++
      continue
    }
    const choice = trimmed.match(/^\(([A-Za-z])\)\s*(.*)$/)
    if (choice && choice[2].length > 0) {
      chunks.push({
        kind: 'choice',
        letter: choice[1].toUpperCase(),
        rest: choice[2],
      })
      i++
      continue
    }
    if (/^[-•*]\s/.test(trimmed)) {
      const items: string[] = []
      while (i < lines.length) {
        const t = lines[i].trim()
        if (/^[-•*]\s/.test(t)) {
          items.push(t.replace(/^[-•*]\s+/, ''))
          i++
        } else break
      }
      chunks.push({ kind: 'bullets', items })
      continue
    }
    if (isPipeDenseLine(trimmed)) {
      const first = extractPipeTableFromLine(trimmed)
      const rows: string[] = [first.pipeLine]
      const caption = first.caption
      i++
      while (i < lines.length) {
        const t = lines[i].trim()
        if (!t) break
        if (!isPipeDenseLine(t)) break
        const next = extractPipeTableFromLine(t)
        if (next.caption) break
        rows.push(next.pipeLine)
        i++
      }
      chunks.push({ kind: 'pipe_table', rows, caption })
      continue
    }
    const paraLines: string[] = []
    while (i < lines.length) {
      const t = lines[i].trim()
      if (!t) break
      if (
        /^(#{1,3})\s+/.test(t) ||
        /^(?:\d+\)|\d+\.\s)/.test(t) ||
        /^\([A-Za-z]\)\s/.test(t) ||
        /^[-•*]\s/.test(t) ||
        isPipeDenseLine(t)
      ) {
        break
      }
      paraLines.push(t)
      i++
    }
    chunks.push({ kind: 'paragraph', lines: paraLines })
  }
  return chunks
}

function NumberedBlock({ raw }: { raw: string }) {
  const segments = raw
    .split(/\s+[—–]\s+/)
    .map((s) => s.trim())
    .filter(Boolean)
  const [head, ...rest] = segments
  return (
    <div className="rounded-xl border border-slate-200/90 border-l-4 border-l-sky-500 bg-white py-3.5 pl-4 pr-3.5 shadow-sm ring-1 ring-slate-900/[0.03]">
      {head ? (
        <p className="text-[0.9375rem] font-semibold leading-snug text-slate-900">
          {renderInlineBold(head)}
        </p>
      ) : null}
      {rest.length > 0 ? (
        <ul className="mt-3 flex list-none flex-col gap-2 pl-0 sm:flex-row sm:flex-wrap">
          {rest.map((seg, si) => (
            <li
              key={si}
              className="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2 text-[0.8125rem] font-medium leading-snug text-slate-700"
            >
              {renderInlineBold(seg)}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  )
}

/**
 * Agrupa linhas em parágrafos, secções e listas para leitura confortável
 * (hierarquia, ritmo vertical, negrito e cartões para rankings).
 */
function AssistantMessageBody({ content }: { content: string }) {
  const lines = content.split('\n')
  let chunks = parseAssistantChunks(lines)
  while (chunks.length > 0 && chunks[0].kind === 'spacer') {
    chunks = chunks.slice(1)
  }
  while (chunks.length > 0 && chunks[chunks.length - 1].kind === 'spacer') {
    chunks = chunks.slice(0, -1)
  }
  const collapsed: AssistantChunk[] = []
  for (const c of chunks) {
    if (
      c.kind === 'spacer' &&
      collapsed.length > 0 &&
      collapsed[collapsed.length - 1].kind === 'spacer'
    ) {
      continue
    }
    collapsed.push(c)
  }
  chunks = collapsed
  return (
    <div className="assistant-message max-w-[min(100%,68ch)] text-[0.9375rem] leading-[1.7] tracking-normal text-slate-800">
      {chunks.map((chunk, idx) => {
        const key = `c-${idx}`
        switch (chunk.kind) {
          case 'spacer':
            return <div key={key} className="h-4 shrink-0" aria-hidden />
          case 'heading': {
            const cls =
              chunk.level === 1
                ? 'text-lg font-bold tracking-tight text-slate-900'
                : chunk.level === 2
                  ? 'text-base font-bold tracking-tight text-slate-900'
                  : 'text-sm font-semibold tracking-tight text-slate-800'
            const Tag = chunk.level === 1 ? 'h3' : chunk.level === 2 ? 'h4' : 'h5'
            return (
              <Tag
                key={key}
                className={`${cls} mt-6 scroll-mt-4 border-b border-slate-200/90 pb-2 first:mt-0`}
              >
                {renderInlineBold(chunk.text)}
              </Tag>
            )
          }
          case 'numbered':
            return (
              <div key={key} className="mt-4 first:mt-0">
                <NumberedBlock raw={chunk.raw} />
              </div>
            )
          case 'bullets':
            return (
              <ul
                key={key}
                className="my-4 list-none space-y-2.5 rounded-xl border border-slate-200/80 bg-gradient-to-b from-slate-50/95 to-white px-4 py-3.5 shadow-sm"
              >
                {chunk.items.map((item, bi) => (
                  <li
                    key={bi}
                    className="relative pl-6 text-[0.875rem] leading-relaxed text-slate-700 before:absolute before:left-0 before:top-[0.35em] before:h-1.5 before:w-1.5 before:rounded-full before:bg-sky-500 before:content-['']"
                  >
                    {renderInlineBold(item)}
                  </li>
                ))}
              </ul>
            )
          case 'choice':
            return (
              <div
                key={key}
                className="my-3 flex gap-3 rounded-xl border border-indigo-200/70 bg-indigo-50/50 px-3 py-3 sm:items-start"
              >
                <span
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-indigo-600 text-xs font-bold text-white shadow-sm"
                  aria-hidden
                >
                  {chunk.letter}
                </span>
                <p className="min-w-0 flex-1 text-[0.9375rem] leading-relaxed text-slate-700">
                  {renderInlineBold(chunk.rest)}
                </p>
              </div>
            )
          case 'pipe_table':
            return (
              <div key={key} className="my-4 first:mt-0">
                {chunk.caption ? (
                  <p className="mb-2 text-[0.875rem] leading-relaxed text-slate-600">
                    {renderInlineBold(chunk.caption)}
                  </p>
                ) : null}
                <PipeTableView rows={chunk.rows} />
              </div>
            )
          case 'paragraph':
            return (
              <p
                key={key}
                className="my-3 text-slate-700 first:mt-0 last:mb-0 [&:not(:last-child)]:mb-4"
              >
                {chunk.lines.map((ln, li) => (
                  <span key={li} className="block [&:not(:first-child)]:mt-2">
                    {renderInlineBold(ln)}
                  </span>
                ))}
              </p>
            )
          default:
            return null
        }
      })}
    </div>
  )
}

function formatCell(v: string | number | boolean | null | undefined): string {
  if (v === null || v === undefined) return '—'
  if (typeof v === 'boolean') return v ? 'sim' : 'não'
  return String(v)
}

function isContentBlock(b: unknown): b is ContentBlock {
  if (!b || typeof b !== 'object') return false
  const t = (b as { type?: string }).type
  switch (t) {
    case 'paragraph':
      return typeof (b as { text?: unknown }).text === 'string'
    case 'heading': {
      const h = b as { level?: unknown; text?: unknown }
      const lv = h.level
      return (
        typeof h.text === 'string' &&
        (lv === undefined || lv === 1 || lv === 2 || lv === 3)
      )
    }
    case 'table': {
      const tb = b as { columns?: unknown; rows?: unknown }
      return Array.isArray(tb.columns) && Array.isArray(tb.rows)
    }
    case 'metric_grid': {
      const mg = b as { items?: unknown }
      if (!Array.isArray(mg.items)) return false
      return (mg.items as unknown[]).every(
        (it) =>
          it &&
          typeof it === 'object' &&
          typeof (it as { label?: unknown }).label === 'string' &&
          typeof (it as { value?: unknown }).value === 'string',
      )
    }
    default:
      return false
  }
}

function parseContentBlocks(raw: unknown): ContentBlocksPayload | null {
  if (raw === null || raw === undefined) return null
  if (typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  if (o.version !== 1 || !Array.isArray(o.blocks)) return null
  const blocks = o.blocks.filter(isContentBlock)
  if (blocks.length === 0) return null
  return { version: 1, blocks }
}

function ContentBlocksView({ blocks }: { blocks: ContentBlock[] }) {
  return (
    <div className="content-blocks space-y-4 border-t border-slate-200/90 pt-4 mt-1">
      {blocks.map((block, i) => {
        const key = `b-${i}`
        switch (block.type) {
          case 'paragraph':
            return (
              <p
                key={key}
                className="text-[0.9375rem] leading-7 text-slate-700 whitespace-pre-wrap"
              >
                {block.text}
              </p>
            )
          case 'heading': {
            const level = block.level ?? 2
            const cls =
              level === 1
                ? 'text-lg font-bold text-slate-900'
                : level === 2
                  ? 'text-base font-semibold text-slate-900'
                  : 'text-sm font-semibold text-slate-800'
            const Tag = level === 1 ? 'h3' : level === 2 ? 'h4' : 'h5'
            return (
              <Tag key={key} className={cls}>
                {block.text}
              </Tag>
            )
          }
          case 'table':
            return (
              <div
                key={key}
                className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm"
              >
                <table className="min-w-full text-left text-[0.8125rem] text-slate-800">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50">
                      {block.columns.map((col, ci) => (
                        <th
                          key={ci}
                          className="whitespace-nowrap px-3 py-2 font-semibold text-slate-700"
                        >
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {block.rows.map((row, ri) => (
                      <tr
                        key={ri}
                        className="border-b border-slate-100 last:border-0 odd:bg-white even:bg-slate-50/60"
                      >
                        {block.columns.map((_, ci) => (
                          <td key={ci} className="px-3 py-2 align-top tabular-nums">
                            {formatCell(row[ci])}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )
          case 'metric_grid':
            return (
              <ul
                key={key}
                className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3 list-none p-0 m-0"
              >
                {block.items.map((item, mi) => (
                  <li
                    key={mi}
                    className="rounded-xl border border-slate-200/95 bg-slate-50/90 px-3 py-2.5 shadow-sm"
                  >
                    <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                      {item.label}
                    </div>
                    <div className="mt-1 text-sm font-semibold tabular-nums text-slate-900">
                      {item.value}
                    </div>
                  </li>
                ))}
              </ul>
            )
          default:
            return null
        }
      })}
    </div>
  )
}

function StructuredAssistantMessage({
  content,
  contentBlocks,
}: {
  content: string
  contentBlocks?: ContentBlocksPayload | null
}) {
  const hasBlocks =
    contentBlocks != null && contentBlocks.blocks.length > 0
  if (!hasBlocks) {
    return <AssistantMessageBody content={content} />
  }
  return (
    <div className="assistant-structured space-y-4">
      {content.trim() ? <AssistantMessageBody content={content} /> : null}
      <ContentBlocksView blocks={contentBlocks.blocks} />
    </div>
  )
}

function PipelineDots() {
  return (
    <div className="mb-2 flex gap-1.5" aria-hidden>
      {[0, 1, 2].map((d) => (
        <span
          key={d}
          className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-sky-500"
          style={{ animationDelay: `${d * 180}ms` }}
        />
      ))}
    </div>
  )
}

function PipelineStatusBlock({
  stepIndex,
  compact,
}: {
  stepIndex: number
  compact?: boolean
}) {
  const label = PIPELINE_STEPS[stepIndex % PIPELINE_STEPS.length]
  if (compact) {
    return (
      <div className="p-3 text-xs text-slate-400">
        <PipelineDots />
        <p className="font-medium leading-snug text-slate-300">{label}</p>
      </div>
    )
  }
  return (
    <div className="flex justify-start">
      <div className="max-w-[85%] rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-600 shadow-sm">
        <PipelineDots />
        <p className="text-sm font-medium text-slate-700">{label}</p>
        <p className="mt-1.5 text-[11px] leading-snug text-slate-500">
          O assistente está a trabalhar — pode demorar alguns segundos.
        </p>
      </div>
    </div>
  )
}

function shortId(uuid: string | null): string {
  if (!uuid) return 'Aguardando primeira msg…'
  return uuid.slice(0, 8)
}

function formatWhen(iso: string | null): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleString('pt-PT', {
      day: '2-digit',
      month: 'short',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return iso
  }
}

// /** Normaliza ``trace_run_id`` vindo do JSON (string, UUID como texto, null). */
// function parseTraceRunId(value: unknown): string | null {
//   if (value === null || value === undefined) return null
//   const s = String(value).trim()
//   return s.length > 0 ? s : null
// }

function contentToString(content: unknown): string {
  if (content === null || content === undefined) return ''
  if (typeof content === 'string') return content
  try {
    return JSON.stringify(content, null, 0)
  } catch {
    return String(content)
  }
}

function mapStoredMessages(raw: StoredMsg[]): ChatMessage[] {
  const out: ChatMessage[] = []
  for (const m of raw) {
    const r = m.role ?? 'user'
    const c = contentToString(m.content)
    if (r === 'tool') continue
    if (r === 'user') out.push({ role: 'user', content: c })
    else if (r === 'assistant')
      out.push({ role: 'assistant', content: c, contentBlocks: null })
    else out.push({ role: 'assistant', content: `[${r}] ${c}` })
  }
  return out
}

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [input, setInput] = useState('')
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [traceRunId, setTraceRunId] = useState<string | null>(null)
  const [agentUsed, setAgentUsed] = useState<string | null>(null)
  const [sessions, setSessions] = useState<SessionRow[]>([])
  const [persistenceEnabled, setPersistenceEnabled] = useState(true)
  const [loading, setLoading] = useState(false)
  const [sessionsLoading, setSessionsLoading] = useState(false)
  const [sessionDetailLoading, setSessionDetailLoading] = useState<string | null>(
    null,
  )
  const [error, setError] = useState<string | null>(null)
  const [pipelineStep, setPipelineStep] = useState(0)
  const messagesScrollRef = useRef<HTMLDivElement>(null)

  const workPending =
    sessionsLoading || loading || sessionDetailLoading !== null

  useEffect(() => {
    if (!workPending) {
      setPipelineStep(0)
      return
    }
    const id = window.setInterval(() => {
      setPipelineStep((s) => (s + 1) % PIPELINE_STEPS.length)
    }, 13500)
    return () => clearInterval(id)
  }, [workPending])

  const scrollMessagesToBottom = useCallback(() => {
    const el = messagesScrollRef.current
    if (!el) return
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        el.scrollTo({ top: el.scrollHeight, behavior: 'smooth' })
      })
    })
  }, [])

  useEffect(() => {
    scrollMessagesToBottom()
  }, [
    messages,
    loading,
    sessionDetailLoading,
    pipelineStep,
    scrollMessagesToBottom,
  ])

  const loadSessions = useCallback(async () => {
    setSessionsLoading(true)
    try {
      const q = demoUserId
        ? `?user_id=${encodeURIComponent(demoUserId)}&limit=50`
        : '?limit=50'
      const res = await fetch(`/api/sessions${q}`)
      if (!res.ok) throw new Error(`Sessões: ${res.status}`)
      const data = (await res.json()) as {
        sessions: SessionRow[]
        persistence_enabled?: boolean
      }
      setSessions(data.sessions ?? [])
      setPersistenceEnabled(data.persistence_enabled !== false)
    } catch {
      setSessions([])
    } finally {
      setSessionsLoading(false)
    }
  }, [])

  useEffect(() => {
    void loadSessions()
  }, [loadSessions])

  function newConversation() {
    setSessionId(null)
    setTraceRunId(null)
    setAgentUsed(null)
    setMessages([])
    setError(null)
    setSessionDetailLoading(null)
  }

  async function selectSession(row: SessionRow) {
    setError(null)
    setSessionDetailLoading(row.session_id)
    try {
      const res = await fetch(`/api/sessions/${row.session_id}`)
      if (!res.ok) {
        const t = await res.text()
        throw new Error(t || `Sessão: ${res.status}`)
      }
      const data = (await res.json()) as SessionDetailResponse
      setSessionId(String(data.session.session_id ?? null))
      setAgentUsed(String(data.session.current_agent ?? null))
      setTraceRunId(String(data.trace_run_id ?? null))
      setMessages(mapStoredMessages(data.messages ?? []))
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Falha ao carregar sessão'
      setError(msg)
    } finally {
      setSessionDetailLoading(null)
    }
  }

  async function sendMessage(e?: SubmitEvent<HTMLFormElement>) {
    e?.preventDefault()
    const text = input.trim()
    if (!text || loading) return
    setInput('')
    setError(null)
    setMessages((m) => [...m, { role: 'user', content: text }])
    setLoading(true)

    try {
      const payload: Record<string, unknown> = { message: text }
      if (demoUserId) payload.user_id = demoUserId
      if (sessionId) payload.session_id = sessionId
      if (agentUsed) payload.target_agent = agentUsed
      if (traceRunId) payload.trace_run_id = traceRunId

      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })

      if (!res.ok) {
        const errBody = await res.text()
        throw new Error(errBody || `Erro ${res.status}`)
      }

      const raw = (await res.json()) as Record<string, unknown> & ChatResponse
      const contentBlocks = parseContentBlocks(raw.content_blocks)
      setMessages((m) => [
        ...m,
        {
          role: 'assistant',
          content: raw.reply ?? '',
          contentBlocks,
        },
      ])
      if (raw.session_id) setSessionId(String(raw.session_id))
      if (raw.trace_run_id) setTraceRunId(String(raw.trace_run_id))
      if (raw.agent_used) setAgentUsed(String(raw.agent_used))
      void loadSessions()
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Falha no pedido'
      setError(msg)
      setMessages((m) => m.slice(0, -1))
    } finally {
      setLoading(false)
    }
  }

  const emptyMain =
    messages.length === 0 && !sessionDetailLoading && !sessionId
  const emptySessionNoMsgs =
    messages.length === 0 && sessionId && !sessionDetailLoading

  return (
    <div className="flex h-full min-h-0 bg-slate-100">
      <aside className="flex w-80 shrink-0 flex-col border-r border-slate-800/80 bg-slate-950 text-slate-100">
        <header className="flex items-center gap-2 border-b border-slate-800 px-4 py-4">
          <span className="text-2xl" aria-hidden>
            🤖
          </span>
          <h1 className="text-lg font-semibold tracking-tight text-white">
            SmartChat
          </h1>
        </header>

        <div className="p-3">
          <button
            type="button"
            onClick={newConversation}
            className="w-full rounded-lg bg-slate-800 px-3 py-2.5 text-sm font-medium text-white transition hover:bg-slate-700"
          >
            + Nova conversa
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col px-3 pb-2">
          <div className="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
            <span className="font-mono text-[10px] text-slate-500">&lt;/&gt;</span>
            Histórico de conversas
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto rounded-lg border border-slate-800 bg-slate-900/50">
            {sessionsLoading ? (
              <PipelineStatusBlock stepIndex={pipelineStep} compact />
            ) : !persistenceEnabled ? (
              <p className="p-3 text-xs text-slate-500">
                PostgreSQL inactivo — sem histórico persistido.
              </p>
            ) : sessions.length === 0 ? (
              <p className="p-3 text-xs text-slate-500">Nenhuma sessão ainda.</p>
            ) : (
              <ul className="divide-y divide-slate-800">
                {sessions.map((s) => {
                  const active = s.session_id === sessionId
                  const busy = sessionDetailLoading === s.session_id
                  return (
                    <li key={s.session_id}>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void selectSession(s)}
                        className={`w-full px-3 py-2.5 text-left text-xs transition hover:bg-slate-800/80 disabled:opacity-50 ${active ? 'bg-emerald-950/40 ring-1 ring-inset ring-emerald-700/50' : ''
                          }`}
                      >
                        <div className="font-mono text-emerald-400">
                          {shortId(s.session_id)}
                          {busy ? ' …' : ''}
                        </div>
                        <div className="mt-0.5 text-violet-300">
                          {s.current_agent}
                        </div>
                        <div className="mt-0.5 text-slate-500">
                          {formatWhen(s.last_active_at)}
                        </div>
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>
        </div>

        <div className="mt-auto space-y-2 border-t border-slate-800 p-3">
          <div className="rounded-md border border-slate-800 bg-slate-900/80 px-2.5 py-2">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              Sessão activa
            </div>
            <div className="mt-1 font-mono text-xs text-emerald-400">
              {shortId(sessionId)}
            </div>
          </div>
          <div className="rounded-md border border-slate-800 bg-slate-900/80 px-2.5 py-2">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              Trace run
            </div>
            <div className="mt-1 font-mono text-xs text-sky-300 break-all">
              {traceRunId ?? 'Aguardando primeira msg…'}
            </div>
          </div>
          <div className="rounded-md border border-slate-800 bg-slate-900/80 px-2.5 py-2">
            <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
              Agente actual
            </div>
            <div className="mt-1 font-mono text-xs text-violet-300">
              {agentUsed ? agentUsed : 'Nenhum (Maestro)'}
            </div>
          </div>
          <p className="text-[10px] leading-snug text-slate-600">
            O <span className="font-mono">session_id</span>,{' '}
            <span className="font-mono">target_agent</span> (eco do último{' '}
            <span className="font-mono">agent_used</span>) e{' '}
            <span className="font-mono">user_id</span> opcional são enviados no
            próximo pedido.
          </p>
        </div>
      </aside>

      <main className="flex min-w-0 flex-1 flex-col bg-white">
        <div
          ref={messagesScrollRef}
          className="min-h-0 flex-1 overflow-y-auto"
        >
          {sessionDetailLoading ? (
            <div className="flex h-full min-h-[320px] flex-col items-center justify-center px-6 py-8">
              <div className="w-full max-w-md">
                <PipelineStatusBlock stepIndex={pipelineStep} />
              </div>
            </div>
          ) : emptyMain ? (
            <div className="flex h-full min-h-[320px] flex-col items-center justify-center px-6 py-8 text-slate-600">
              <span className="mb-4 text-6xl opacity-20" aria-hidden>
                🤖
              </span>
              <div className="max-w-lg text-center">
                <p className="text-sm text-slate-500">
                  Envie uma mensagem para começar. A primeira mensagem irá gerar um{' '}
                  <code className="rounded bg-slate-100 px-1 font-mono text-xs text-slate-700">
                    session_id
                  </code>{' '}
                  (com PostgreSQL activo) e o contexto será mantido nas próximas.
                </p>
                <p className="mt-6 text-xs font-semibold uppercase tracking-wide text-slate-400">
                  O que pode perguntar
                </p>
                <ul className="mt-3 list-disc space-y-2 pl-5 text-left text-sm leading-snug text-slate-600">
                  {EMPTY_STATE_TOPICS.map((topic) => (
                    <li key={topic.id}>{topic.text}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : emptySessionNoMsgs ? (
            <div className="flex h-full min-h-[320px] flex-col items-center justify-center px-6 text-center text-slate-500">
              <p className="max-w-md text-sm">
                Esta sessão ainda não tem mensagens de especialista persistidas
                (o roteamento do Maestro não é guardado na base). Pode continuar a
                conversa abaixo.
              </p>
            </div>
          ) : (
            <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
              {messages.map((msg, i) => (
                <div
                  key={`${i}-${msg.role}`}
                  className={`flex min-w-0 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`rounded-2xl ${msg.role === 'user'
                        ? 'max-w-[85%] bg-slate-800 px-4 py-2.5 text-sm leading-relaxed text-white'
                        : 'w-full min-w-0 max-w-[min(100%,48rem)] border border-slate-200/90 bg-gradient-to-b from-slate-50/95 to-white px-4 py-4 text-slate-800 shadow-sm ring-1 ring-slate-900/[0.04] sm:px-6 sm:py-5'
                      }`}
                  >
                    {msg.role === 'user' ? (
                      <span className="block whitespace-pre-wrap break-words">
                        {msg.content}
                      </span>
                    ) : (
                      <StructuredAssistantMessage
                        content={msg.content}
                        contentBlocks={msg.contentBlocks}
                      />
                    )}
                  </div>
                </div>
              ))}
              {loading ? (
                <PipelineStatusBlock stepIndex={pipelineStep} />
              ) : null}
            </div>
          )}
        </div>

        <div className="border-t border-slate-200 bg-white px-4 py-3">
          {error && (
            <div className="mb-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800">
              {error}
            </div>
          )}
          <form onSubmit={sendMessage} className="mx-auto flex max-w-3xl gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Digite sua mensagem aqui…"
              disabled={loading}
              className="min-w-0 flex-1 rounded-xl border border-slate-300 bg-slate-50 px-4 py-3 text-sm outline-none ring-slate-400 focus:border-sky-500 focus:ring-2 disabled:opacity-60"
            />
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-sky-600 text-white transition hover:bg-sky-500 disabled:opacity-40"
              aria-label="Enviar"
            >
              <svg
                xmlns="http://www.w3.org/2000/svg"
                viewBox="0 0 24 24"
                fill="currentColor"
                className="h-5 w-5"
              >
                <path d="M3.478 2.404a.75.75 0 0 0-.926.941l2.432 7.905H13.5a.75.75 0 0 1 0 1.5H4.984l-2.432 7.905a.75.75 0 0 0 .926.94 60.519 60.519 0 0 0 18.445-8.986.75.75 0 0 0 0-1.218A60.517 60.517 0 0 0 3.478 2.404Z" />
              </svg>
            </button>
          </form>
          <p className="mx-auto mt-2 max-w-3xl text-center text-[11px] text-slate-500">
            A IA pode cometer erros. Considere verificar as informações importantes.
          </p>
        </div>
      </main>
    </div>
  )
}
