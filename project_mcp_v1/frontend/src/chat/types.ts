export type ContentBlock =
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

export type ContentBlocksPayload = { version: 1; content_blocks: ContentBlock[] }

export type ChatMessage =
  | { role: 'user'; content: string }
  | {
      role: 'assistant'
      content: string
      contentBlocks?: ContentBlocksPayload | null
    }

export type SessionRow = {
  session_id: string
  user_id: string | null
  current_agent: string
  status: string
  started_at: string | null
  last_active_at: string | null
}

export type ChatResponse = {
  reply: string
  content_blocks?: ContentBlocksPayload | null
  tools_used: unknown[]
  agent_used: string
  trace_run_id?: string | null
  session_id?: string
  user_id?: string
}

export type SessionDetailResponse = {
  session: SessionRow & { metadata?: Record<string, unknown> }
  messages: StoredMsg[]
  trace_run_id: string | null
  persistence_enabled?: boolean
}

export type StoredMsg = {
  role?: string
  content?: unknown
  name?: string
}
