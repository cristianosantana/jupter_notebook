import {
  type AssistantChunk,
  parseAssistantChunks,
} from '../../assistant/assistantChunks'
import { NumberedBlock } from './NumberedBlock'
import { PipeTableView } from './PipeTableView'
import { renderInlineBold } from './renderInlineBold'

/**
 * Agrupa linhas em parágrafos, secções e listas para leitura confortável
 * (hierarquia, ritmo vertical, negrito e cartões para rankings).
 */
export function AssistantMessageBody({ content }: { content: string }) {
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
  const prose = 'assistant-prose-width'
  return (
    <div className="assistant-message">
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
              <div key={key} className={prose}>
                <Tag
                  className={`${cls} mt-6 scroll-mt-4 border-b border-slate-200/90 pb-2 first:mt-0`}
                >
                  {renderInlineBold(chunk.text)}
                </Tag>
              </div>
            )
          }
          case 'numbered':
            return (
              <div key={key} className={`mt-4 first:mt-0 ${prose}`}>
                <NumberedBlock raw={chunk.raw} />
              </div>
            )
          case 'bullets':
            return (
              <div key={key} className={prose}>
                <ul className="my-4 list-none space-y-2.5 rounded-xl border border-slate-200/80 bg-gradient-to-b from-slate-50/95 to-white px-4 py-3.5 shadow-sm">
                  {chunk.items.map((item, bi) => (
                    <li
                      key={bi}
                      className="relative pl-6 text-[0.875rem] leading-relaxed text-slate-700 before:absolute before:left-0 before:top-[0.35em] before:h-1.5 before:w-1.5 before:rounded-full before:bg-sky-500 before:content-['']"
                    >
                      {renderInlineBold(item)}
                    </li>
                  ))}
                </ul>
              </div>
            )
          case 'choice':
            return (
              <div key={key} className={prose}>
                <div className="my-3 flex gap-3 rounded-xl border border-indigo-200/70 bg-indigo-50/50 px-3 py-3 sm:items-start">
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
              </div>
            )
          case 'pipe_table':
            return (
              <div key={key} className="my-4 w-full first:mt-0">
                {chunk.caption ? (
                  <p
                    className={`mb-2 text-[0.875rem] leading-relaxed text-slate-600 ${prose}`}
                  >
                    {renderInlineBold(chunk.caption)}
                  </p>
                ) : null}
                <div className="flex w-full justify-center">
                  <div className="min-w-0 max-w-full">
                    <PipeTableView rows={chunk.rows} />
                  </div>
                </div>
              </div>
            )
          case 'paragraph':
            return (
              <div key={key} className={prose}>
                <p className="my-3 text-slate-700 first:mt-0 last:mb-0 [&:not(:last-child)]:mb-4">
                  {chunk.lines.map((ln, li) => (
                    <span key={li} className="block [&:not(:first-child)]:mt-2">
                      {renderInlineBold(ln)}
                    </span>
                  ))}
                </p>
              </div>
            )
          default:
            return null
        }
      })}
    </div>
  )
}
