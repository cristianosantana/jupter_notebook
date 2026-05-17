/**
 * Cliente HTTP para a API de chat do orion_mcp_v3.
 *
 * Base URL:
 * - Dev: proxy Vite → pedidos relativos ``/api/...``
 * - Build: ``VITE_ORION_API_BASE`` (sem barra final).
 */

export type OrionChatRequest = {
  message: string
  conversation_id: string | null
  stream: boolean
  max_tokens: number
  policy: string
}

export type OrionChatResponse = {
  reply: string
  meta: {
    conversation_id: string
    model: string
    finish_reason: string
    latency_ms: number
    usage: {
      prompt_tokens: number
      completion_tokens: number
      total_tokens: number
    }
    safeguards: string[]
    cognitive_intent: string | null
    coverage_note: string
  }
}

export type StoredChatMessage = {
  role: string
  content: string
  created_at: string
  message_id: number
}

export type SessionListItem = {
  conversation_id: string
  turn_count: number
  messages: StoredChatMessage[]
}

export type SessionListResponse = {
  sessions: SessionListItem[]
}

export type ChatOptionsResponse = {
  policies: string[]
  max_tokens_min: number
  max_tokens_max: number
  max_tokens_presets: number[]
  default_max_tokens: number
  default_policy: string
}

export type OrionApiError = {
  error: string
  detail?: string
}

function apiBase(): string {
  const raw = import.meta.env.VITE_ORION_API_BASE?.trim() ?? ''
  return raw.replace(/\/$/, '')
}

function prefix(): string {
  const base = apiBase()
  return base ? `${base}/api/v1` : '/api/v1'
}

export function chatUrl(): string {
  return `${prefix()}/chat`
}

export function sessionsUrl(): string {
  return `${prefix()}/sessions`
}

export function chatOptionsUrl(): string {
  return `${prefix()}/chat/options`
}

export async function fetchChatOptions(): Promise<ChatOptionsResponse> {
  const res = await fetch(chatOptionsUrl(), { headers: { Accept: 'application/json' } })
  const text = await res.text()
  if (!res.ok) throw new Error(`${res.status}: ${text.slice(0, 400)}`)
  return JSON.parse(text) as ChatOptionsResponse
}

export async function fetchSessions(): Promise<SessionListResponse> {
  const res = await fetch(sessionsUrl(), { headers: { Accept: 'application/json' } })
  const text = await res.text()
  if (!res.ok) throw new Error(`${res.status}: ${text.slice(0, 400)}`)
  return JSON.parse(text) as SessionListResponse
}

export async function postChat(req: OrionChatRequest): Promise<OrionChatResponse> {
  const res = await fetch(chatUrl(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify(req),
  })
  const text = await res.text()
  if (!res.ok) {
    let detail = text
    try {
      const j = JSON.parse(text) as OrionApiError
      detail = j.detail || j.error || text
    } catch {
      /* ignore */
    }
    throw new Error(`${res.status} ${res.statusText}: ${detail.slice(0, 800)}`)
  }
  return JSON.parse(text) as OrionChatResponse
}

/** SSE: eventos ``data: {json}`` até um evento com ``done: true``. */
export async function postChatStream(
  req: OrionChatRequest,
  onDelta: (delta: string) => void,
): Promise<{ conversation_id: string; latency_ms?: number; cognitive_intent?: string }> {
  const res = await fetch(chatUrl(), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({ ...req, stream: true }),
  })
  if (!res.ok || !res.body) {
    const t = await res.text().catch(() => '')
    throw new Error(`${res.status}: ${t.slice(0, 500)}`)
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  let meta: { conversation_id: string; latency_ms?: number; cognitive_intent?: string } = {
    conversation_id: '',
  }
  const processBlock = (block: string) => {
    for (const line of block.split('\n')) {
      if (!line.startsWith('data: ')) continue
      const payload = line.slice(6).trim()
      if (!payload) continue
      try {
        const j = JSON.parse(payload) as Record<string, unknown>
        if (typeof j.delta === 'string') onDelta(j.delta)
        if (j.done === true) {
          meta = {
            conversation_id: String(j.conversation_id ?? ''),
            latency_ms: typeof j.latency_ms === 'number' ? j.latency_ms : undefined,
            cognitive_intent: typeof j.cognitive_intent === 'string' ? j.cognitive_intent : undefined,
          }
        }
      } catch {
        /* ignore */
      }
    }
  }
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    const parts = buf.split('\n\n')
    buf = parts.pop() ?? ''
    for (const block of parts) processBlock(block)
  }
  if (buf.trim()) processBlock(buf)
  return meta
}
