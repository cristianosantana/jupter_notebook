import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  chatUrl,
  fetchChatOptions,
  fetchSessions,
  postChat,
  postChatStream,
  type ChatOptionsResponse,
  type SessionListItem,
  type StoredChatMessage,
} from './api/orionChat'

function sessionPreview(messages: StoredChatMessage[] | undefined): string {
  if (!messages?.length) return ''
  const last = messages[messages.length - 1]
  const t = last.content.trim().replace(/\s+/g, ' ')
  return t.length > 100 ? `${t.slice(0, 100)}…` : t
}

function buildChatRequest(
  message: string,
  conversationId: string | null,
  stream: boolean,
  maxTokens: number,
  policy: string,
) {
  return {
    message,
    conversation_id: conversationId,
    stream,
    max_tokens: maxTokens,
    policy,
  }
}

export function App() {
  const [options, setOptions] = useState<ChatOptionsResponse | null>(null)
  const [optionsError, setOptionsError] = useState<string | null>(null)
  const [sessions, setSessions] = useState<SessionListItem[]>([])
  const [sessionsError, setSessionsError] = useState<string | null>(null)

  /** ``null`` = nova conversa: primeira mensagem sem ``conversation_id``; o backend devolve o id em ``meta``. */
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)

  const [message, setMessage] = useState(
    'Qual forma de pagamento domina o faturamento entre janeiro e abril de 2026?',
  )
  const [policy, setPolicy] = useState('balanced')
  const [maxTokens, setMaxTokens] = useState(4096)
  const [stream, setStream] = useState(false)
  const [reply, setReply] = useState('')
  const [metaText, setMetaText] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reloadSessions = useCallback(async () => {
    setSessionsError(null)
    try {
      const r = await fetchSessions()
      setSessions(r.sessions)
    } catch (e) {
      setSessionsError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const o = await fetchChatOptions()
        if (cancelled) return
        setOptions(o)
        setPolicy(o.default_policy)
        setMaxTokens(o.default_max_tokens)
      } catch (e) {
        if (!cancelled) setOptionsError(e instanceof Error ? e.message : String(e))
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    void reloadSessions()
  }, [reloadSessions])

  const endpointLabel = useMemo(() => chatUrl(), [])

  const activeThread = useMemo((): StoredChatMessage[] => {
    if (!activeConversationId) return []
    return sessions.find((s) => s.conversation_id === activeConversationId)?.messages ?? []
  }, [sessions, activeConversationId])

  const maxTokenChoices = useMemo(() => {
    if (!options) return [4096, 8192, 16_384, 20_000]
    const set = new Set(options.max_tokens_presets)
    set.add(options.default_max_tokens)
    set.add(maxTokens)
    return [...set].filter((n) => n >= options.max_tokens_min && n <= options.max_tokens_max).sort((a, b) => a - b)
  }, [options, maxTokens])

  const send = useCallback(async () => {
    setError(null)
    setReply('')
    setMetaText('')
    const trimmed = message.trim()
    if (!trimmed) {
      setError('Escreva uma mensagem.')
      return
    }
    if (options) {
      if (maxTokens < options.max_tokens_min || maxTokens > options.max_tokens_max) {
        setError(`max_tokens deve estar entre ${options.max_tokens_min} e ${options.max_tokens_max}.`)
        return
      }
    } else if (maxTokens < 64 || maxTokens > 32000) {
      setError('max_tokens inválido.')
      return
    }
    setLoading(true)
    try {
      const payload = buildChatRequest(trimmed, activeConversationId, stream, maxTokens, policy)
      if (stream) {
        let acc = ''
        const m = await postChatStream(payload, (d) => {
          acc += d
          setReply(acc)
        })
        setMetaText(
          JSON.stringify(
            { conversation_id: m.conversation_id, latency_ms: m.latency_ms, cognitive_intent: m.cognitive_intent },
            null,
            2,
          ),
        )
        if (m.conversation_id) setActiveConversationId(m.conversation_id)
      } else {
        const data = await postChat(payload)
        setReply(data.reply)
        setMetaText(JSON.stringify(data.meta, null, 2))
        if (data.meta.conversation_id) setActiveConversationId(data.meta.conversation_id)
      }
      await reloadSessions()
      setReply('')
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [activeConversationId, maxTokens, message, options, policy, reloadSessions, stream])

  const newConversation = () => {
    setActiveConversationId(null)
    setReply('')
    setMetaText('')
    setError(null)
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="sidebar-head">
          <h2 className="sidebar-title">Sessões</h2>
          <button type="button" className="btn secondary btn-sm" onClick={() => void reloadSessions()}>
            Actualizar
          </button>
        </div>
        <button type="button" className="btn primary btn-block" onClick={newConversation}>
          Nova conversa
        </button>
        {sessionsError ? <p className="sidebar-err">{sessionsError}</p> : null}
        <ul className="session-list">
          <li>
            <button
              type="button"
              className={`session-item ${activeConversationId === null ? 'active' : ''}`}
              onClick={newConversation}
            >
              <span className="session-id">(sem id — próximo envio cria)</span>
              <span className="session-hint">Primeira mensagem não envia conversation_id</span>
            </button>
          </li>
          {sessions.map((s) => (
            <li key={s.conversation_id}>
              <button
                type="button"
                className={`session-item ${activeConversationId === s.conversation_id ? 'active' : ''}`}
                onClick={() => {
                  setActiveConversationId(s.conversation_id)
                  setReply('')
                  setMetaText('')
                  setError(null)
                }}
              >
                <span className="session-id mono">{s.conversation_id.slice(0, 8)}…</span>
                {sessionPreview(s.messages) ? (
                  <span className="session-preview">{sessionPreview(s.messages)}</span>
                ) : null}
                <span className="session-meta">
                  {s.messages?.length ?? 0} msg · {s.turn_count} turno(s)
                </span>
              </button>
            </li>
          ))}
        </ul>
      </aside>

      <div className="shell">
        <header className="header">
          <h1>Orion MCP — Chat</h1>
          <p className="muted">
            <code>POST {endpointLabel}</code> — primeira mensagem:{' '}
            <code>conversation_id: null</code>; respostas seguintes usam o id devolvido em{' '}
            <code>meta.conversation_id</code>.
          </p>
          {optionsError ? <p className="warn">Opções da API: {optionsError}</p> : null}
        </header>

        {activeConversationId && (activeThread.length > 0 || (stream && reply)) ? (
          <section className="card thread-card">
            <h2 className="thread-title">Histórico da sessão</h2>
            <div className="thread">
              {activeThread.map((m) => (
                <div key={m.message_id} className={`msg msg-${m.role === 'user' ? 'user' : 'assistant'}`}>
                  <div className="msg-meta">
                    <span className="msg-role">{m.role}</span>
                    <time className="msg-time" dateTime={m.created_at}>
                      {m.created_at}
                    </time>
                  </div>
                  <div className="msg-body">{m.content}</div>
                </div>
              ))}
              {stream && reply ? (
                <div className="msg msg-assistant msg-pending">
                  <div className="msg-meta">
                    <span className="msg-role">assistant</span>
                    <span className="msg-time">a receber…</span>
                  </div>
                  <div className="msg-body">{reply}</div>
                </div>
              ) : null}
            </div>
          </section>
        ) : null}

        <section className="card">
          <p className="field-hint">
            Sessão activa:{' '}
            {activeConversationId === null ? (
              <em>nova (sem id até à primeira resposta)</em>
            ) : (
              <code className="mono">{activeConversationId}</code>
            )}
          </p>

          <label className="field">
            <span>message</span>
            <textarea
              className="textarea"
              rows={5}
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="A sua pergunta…"
            />
          </label>

          <div className="grid2">
            <label className="field">
              <span>policy</span>
              <select
                className="input"
                value={policy}
                onChange={(e) => setPolicy(e.target.value)}
                disabled={!options?.policies.length}
              >
                {(options?.policies ?? ['balanced']).map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>max_tokens</span>
              <select
                className="input"
                value={String(maxTokens)}
                onChange={(e) => setMaxTokens(Number(e.target.value))}
                disabled={!maxTokenChoices.length}
              >
                {maxTokenChoices.map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <label className="inline">
            <input type="checkbox" checked={stream} onChange={(e) => setStream(e.target.checked)} />
            <span>stream (SSE)</span>
          </label>

          <div className="actions">
            <button type="button" className="btn primary" disabled={loading} onClick={() => void send()}>
              {loading ? 'A enviar…' : 'Enviar'}
            </button>
          </div>
        </section>

        {error ? (
          <section className="card error">
            <h2>Erro</h2>
            <pre>{error}</pre>
          </section>
        ) : null}

        {metaText ? (
          <section className="card">
            <h2>Meta</h2>
            <pre className="meta">{metaText}</pre>
          </section>
        ) : null}

        <footer className="footer muted">
          <p>
            <code>GET /api/v1/sessions</code>, <code>GET /api/v1/chat/options</code>. API:{' '}
            <code>uvicorn orion_mcp_v3.api.main:app</code> (porta 8000).
          </p>
        </footer>
      </div>
    </div>
  )
}
