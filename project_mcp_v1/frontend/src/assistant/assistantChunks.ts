import {
  extractPipeTableFromLine,
  isPipeDenseLine,
} from './pipeTable'

export type AssistantChunk =
  | { kind: 'spacer' }
  | { kind: 'heading'; level: 1 | 2 | 3; text: string }
  | { kind: 'numbered'; raw: string }
  | { kind: 'bullets'; items: string[] }
  | { kind: 'paragraph'; lines: string[] }
  | { kind: 'choice'; letter: string; rest: string }
  | { kind: 'pipe_table'; rows: string[]; caption: string | null }

export function parseAssistantChunks(lines: string[]): AssistantChunk[] {
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
