import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type SubmitEvent,
} from 'react'
import { parseContentBlocks } from '../assistant/parseContentBlocks'
import { mapStoredMessages } from '../chat/apiMapMessages'
import { demoUserId, PIPELINE_STEPS } from '../chat/constants'
import type {
  ChatMessage,
  ChatResponse,
  SessionDetailResponse,
  SessionRow,
} from '../chat/types'
import { PipelineStatusBlock } from '../components/assistant/PipelineStatusBlock'
import { ChatComposer } from '../components/chat/ChatComposer'
import { ChatEmptyState } from '../components/chat/ChatEmptyState'
import { ChatLayout } from '../components/chat/ChatLayout'
import { MessageThread } from '../components/chat/MessageThread'
import { SessionsSidebar } from '../components/chat/SessionsSidebar'
import type { EmptyStateTopic } from '../components/emptyState/emptyStateTopics'

function isAbortError(err: unknown): boolean {
  if (err instanceof DOMException && err.name === 'AbortError') return true
  if (err instanceof Error && err.name === 'AbortError') return true
  return false
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
  const chatInputRef = useRef<HTMLTextAreaElement>(null)
  const chatAbortRef = useRef<AbortController | null>(null)

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

  const cancelChat = useCallback(() => {
    chatAbortRef.current?.abort()
  }, [])

  async function sendMessage(e?: SubmitEvent<HTMLFormElement>) {
    e?.preventDefault()
    const text = input.trim()
    if (!text || loading) return

    chatAbortRef.current?.abort()
    const ac = new AbortController()
    chatAbortRef.current = ac

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
        signal: ac.signal,
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
      if (isAbortError(err)) {
        setInput(text)
        setMessages((m) => m.slice(0, -1))
      } else {
        const msg = err instanceof Error ? err.message : 'Falha no pedido'
        setError(msg)
        setMessages((m) => m.slice(0, -1))
      }
    } finally {
      chatAbortRef.current = null
      setLoading(false)
    }
  }

  const pickEmptyTopic = useCallback((topic: EmptyStateTopic) => {
    setInput(topic.text)
    setError(null)
    queueMicrotask(() => {
      chatInputRef.current?.focus()
      chatInputRef.current?.scrollIntoView({
        block: 'nearest',
        behavior: 'smooth',
      })
    })
  }, [])

  const emptyMain =
    messages.length === 0 && !sessionDetailLoading && !sessionId
  const emptySessionNoMsgs =
    messages.length === 0 && sessionId && !sessionDetailLoading

  return (
    <ChatLayout
      emptyMain={emptyMain}
      sidebar={
        <SessionsSidebar
          onNewConversation={newConversation}
          sessionsLoading={sessionsLoading}
          persistenceEnabled={persistenceEnabled}
          sessions={sessions}
          sessionId={sessionId}
          sessionDetailLoading={sessionDetailLoading}
          onSelectSession={selectSession}
          traceRunId={traceRunId}
          agentUsed={agentUsed}
          pipelineStep={pipelineStep}
        />
      }
    >
      <div ref={messagesScrollRef} className="chat-messages-scroll">
        {sessionDetailLoading ? (
          <div className="chat-loading-center">
            <div className="w-full max-w-md">
              <PipelineStatusBlock stepIndex={pipelineStep} />
            </div>
          </div>
        ) : emptyMain ? (
          <ChatEmptyState
            error={error}
            input={input}
            setInput={setInput}
            loading={loading}
            sendMessage={sendMessage}
            chatInputRef={chatInputRef}
            onPickTopic={pickEmptyTopic}
            onCancelChat={cancelChat}
          />
        ) : emptySessionNoMsgs ? (
          <div className="chat-session-empty-hint">
            <p className="max-w-md text-sm">
              Esta sessão ainda não tem mensagens de especialista persistidas (o
              roteamento do Maestro não é guardado na base). Pode continuar a
              conversa abaixo.
            </p>
          </div>
        ) : (
          <MessageThread
            messages={messages}
            loading={loading}
            pipelineStep={pipelineStep}
          />
        )}
      </div>

      <div
        className={`chat-composer-bar ${emptyMain ? 'chat-composer-bar-empty' : 'chat-composer-bar-filled'}`}
      >
        {!emptyMain ? (
          <ChatComposer
            input={input}
            setInput={setInput}
            loading={loading}
            sendMessage={sendMessage}
            chatInputRef={chatInputRef}
            error={error}
            onCancelChat={cancelChat}
          />
        ) : null}
        <p
          className={`chat-footer-note ${emptyMain ? '' : 'chat-footer-note-spaced'}`}
        >
          A IA pode cometer erros. Considere verificar as informações importantes.
        </p>
      </div>
    </ChatLayout>
  )
}
