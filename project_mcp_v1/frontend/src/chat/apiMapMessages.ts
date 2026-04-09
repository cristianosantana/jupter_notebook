import type { ChatMessage, StoredMsg } from './types'

export function contentToString(content: unknown): string {
  if (content === null || content === undefined) return ''
  if (typeof content === 'string') return content
  try {
    return JSON.stringify(content, null, 0)
  } catch {
    return String(content)
  }
}

export function mapStoredMessages(raw: StoredMsg[]): ChatMessage[] {
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
