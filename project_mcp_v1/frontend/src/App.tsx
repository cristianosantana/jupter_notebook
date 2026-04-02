import { useCallback, useEffect, useRef, useState } from 'react'
import type { SubmitEvent } from 'react'

type ChatMessage =
  | { role: 'user'; content: string }
  | { role: 'assistant'; content: string }

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
    else if (r === 'assistant') out.push({ role: 'assistant', content: c })
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
      setMessages((m) => [
        ...m,
        { role: 'assistant', content: raw.reply ?? '' },
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
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  <div
                    className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${msg.role === 'user'
                        ? 'bg-slate-800 text-white'
                        : 'border border-slate-200 bg-slate-50 text-slate-800'
                      }`}
                  >
                    <span className="block whitespace-pre-wrap break-words">
                      {msg.content}
                    </span>
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
