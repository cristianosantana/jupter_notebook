import { useMemo } from 'react'
import {
  extractTsvTableFromProse,
  peekTsvDataRowCount,
  stripDuplicateConcessionariaList,
} from '../../dedupeAssistantProse'
import type { ContentBlocksPayload } from '../../chat/types'
import { extractReplyContentBlocks } from '../../assistant/parseContentBlocks'
import { AssistantMessageBody } from './AssistantMessageBody'
import { ContentBlocksView } from './ContentBlocksView'
import { TsvInlineTableView } from './TsvInlineTableView'

export function StructuredAssistantMessage({
  content,
  contentBlocks,
}: {
  content: string
  contentBlocks?: ContentBlocksPayload | null
}) {
  const { displayContent, mergedBlocks, tsvInline } = useMemo(() => {
    const extracted = extractReplyContentBlocks(content)
    const fromApi =
      contentBlocks != null && contentBlocks.blocks.length > 0
        ? contentBlocks
        : null
    const payload = extracted.payload
    const blocks = fromApi ?? payload
    let text = payload != null ? extracted.displayText : content

    const jsonTableMaxRows =
      blocks?.blocks.reduce((m, b) => {
        if (b.type === 'table') return Math.max(m, b.rows.length)
        return m
      }, 0) ?? 0

    const tsvPeek = peekTsvDataRowCount(text)
    const refRows = Math.max(jsonTableMaxRows, tsvPeek ?? 0)
    if (refRows >= 3) {
      text = stripDuplicateConcessionariaList(text, refRows)
    }

    const { proseWithoutTable, table: tsvRaw } = extractTsvTableFromProse(text)
    const hasJsonTable = blocks?.blocks.some(
      (b) => b.type === 'table' && b.rows.length >= 2,
    )
    const tsvInline = hasJsonTable ? null : tsvRaw

    return {
      displayContent: proseWithoutTable,
      mergedBlocks: blocks,
      tsvInline,
    }
  }, [content, contentBlocks])

  const hasStructured =
    (mergedBlocks != null && mergedBlocks.blocks.length > 0) || tsvInline != null
  if (!hasStructured) {
    return <AssistantMessageBody content={displayContent} />
  }
  return (
    <div className="assistant-structured">
      {displayContent.trim() ? (
        <AssistantMessageBody content={displayContent} />
      ) : null}
      {mergedBlocks != null && mergedBlocks.blocks.length > 0 ? (
        <ContentBlocksView blocks={mergedBlocks.blocks} />
      ) : null}
      {tsvInline ? <TsvInlineTableView table={tsvInline} /> : null}
    </div>
  )
}
