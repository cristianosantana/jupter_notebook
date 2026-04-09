import { EmptyStateTopicCarousel } from './EmptyStateTopicCarousel'
import { EmptyStateTopicStack } from './EmptyStateTopicStack'
import type { EmptyStateTopic } from './emptyStateTopics'

export type EmptyStateTopicDisplayMode = 'stack' | 'carousel'

type EmptyStateTopicDisplayProps = {
  /** Troque para `carousel` para ver o carrossel; `stack` mantém a pilha 3D. */
  mode: EmptyStateTopicDisplayMode
  topics: EmptyStateTopic[]
  onPick: (t: EmptyStateTopic) => void
}

export function EmptyStateTopicDisplay({
  mode,
  topics,
  onPick,
}: EmptyStateTopicDisplayProps) {
  if (mode === 'carousel') {
    return <EmptyStateTopicCarousel topics={topics} onPick={onPick} />
  }
  return <EmptyStateTopicStack topics={topics} onPick={onPick} />
}
