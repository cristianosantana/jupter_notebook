import type { ContentBlock, ContentBlocksPayload } from '../chat/types'

export function isContentBlock(b: unknown): b is ContentBlock {
  if (!b || typeof b !== 'object') return false
  const t = (b as { type?: string }).type
  switch (t) {
    case 'paragraph':
      return typeof (b as { text?: unknown }).text === 'string'
    case 'heading': {
      const h = b as { level?: unknown; text?: unknown }
      const lv = h.level
      const n = lv === undefined ? 2 : Number(lv)
      return (
        typeof h.text === 'string' &&
        (lv === undefined ||
          lv === 1 ||
          lv === 2 ||
          lv === 3 ||
          n === 1 ||
          n === 2 ||
          n === 3)
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

/** Normaliza chaves comuns geradas pelo modelo (casing, aliases). */
export function normalizeContentBlockRaw(raw: unknown): unknown {
  if (!raw || typeof raw !== 'object') return raw
  const o = raw as Record<string, unknown>
  const out: Record<string, unknown> = { ...o }
  if (typeof out.type === 'string') {
    out.type = out.type.trim().toLowerCase()
  }
  if (out.type === 'table') {
    if (out.columns == null && o.Columns != null) out.columns = o.Columns
    if (out.rows == null && o.Rows != null) out.rows = o.Rows
  }
  if (out.type === 'metric_grid' && out.items == null && o.Items != null) {
    out.items = o.Items
  }
  if (out.type === 'heading' && out.level != null) {
    const n = Number(out.level)
    if (n === 1 || n === 2 || n === 3) out.level = n
  }
  return out
}

export function parseContentBlocks(raw: unknown): ContentBlocksPayload | null {
  if (raw === null || raw === undefined) return null
  if (typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  const ver = o.version
  if (ver !== 1 && ver !== '1') return null
  if (!Array.isArray(o.blocks)) return null
  const blocks = o.blocks
    .map(normalizeContentBlockRaw)
    .filter(isContentBlock) as ContentBlock[]
  if (blocks.length === 0) return null
  return { version: 1, blocks }
}

/**
 * Extrai `content_blocks` de um fence ```json no texto (espelha o backend).
 * Remove o fence do texto mostrado para não “partir” o layout com JSON cru.
 */
export function extractReplyContentBlocks(reply: string): {
  displayText: string
  payload: ContentBlocksPayload | null
} {
  if (!reply?.trim()) {
    return { displayText: reply, payload: null }
  }
  const text = reply
  const re = /```(?:json)?\s*([\s\S]*?)```/gi
  const matches: RegExpMatchArray[] = []
  let m: RegExpExecArray | null
  const r = new RegExp(re.source, re.flags)
  while ((m = r.exec(text)) !== null) {
    matches.push(m)
  }
  for (let i = matches.length - 1; i >= 0; i--) {
    const match = matches[i]
    const raw = (match[1] ?? '').trim()
    if (!raw.startsWith('{')) continue
    try {
      const data = JSON.parse(raw) as unknown
      const payload = parseContentBlocks(data)
      if (!payload) continue
      const full = match[0]
      const startIdx = match.index ?? 0
      const endIdx = startIdx + full.length
      const before = text.slice(0, startIdx).trimEnd()
      const after = text.slice(endIdx).trimStart()
      const displayText = [before, after].filter(Boolean).join('\n\n').trim()
      return { displayText, payload }
    } catch {
      continue
    }
  }
  const stripped = text.trim()
  if (stripped.startsWith('{') && stripped.includes('"blocks"')) {
    try {
      const data = JSON.parse(stripped) as unknown
      const payload = parseContentBlocks(data)
      if (payload) return { displayText: '', payload }
    } catch {
      /* ignore */
    }
  }
  return { displayText: text, payload: null }
}
