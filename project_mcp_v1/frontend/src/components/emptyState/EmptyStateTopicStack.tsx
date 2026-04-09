import { useEffect, useMemo, useState } from 'react'
import { useReducedMotion } from 'framer-motion'
import { EmptyStateTopicCard } from './EmptyStateTopicCard'
import type { EmptyStateTopic } from './emptyStateTopics'
import { StackingTopicCard } from './StackingTopicCard'

/** Tempo entre avanços: deve ser claramente maior que a duração da transição no cartão. */
const ROTATE_INTERVAL_MS = 7000

type EmptyStateTopicStackProps = {
  topics: EmptyStateTopic[]
  onPick: (t: EmptyStateTopic) => void
}

/** Ordem circular: destaque primeiro (topo do contentor), depois os seguintes. */
function topicsInStackOrder(
  topics: EmptyStateTopic[],
  focusIndex: number,
): EmptyStateTopic[] {
  const n = topics.length
  if (n === 0) return []
  const f = ((focusIndex % n) + n) % n
  return topics.map((_, i) => topics[(f + i) % n])
}

export function EmptyStateTopicStack({
  topics,
  onPick,
}: EmptyStateTopicStackProps) {
  const reduceMotion = useReducedMotion()
  const [focusIndex, setFocusIndex] = useState(0)
  const n = topics.length

  const orderedTopics = useMemo(
    () => topicsInStackOrder(topics, focusIndex),
    [topics, focusIndex],
  )

  useEffect(() => {
    if (n <= 1 || reduceMotion) return

    const advance = () => {
      setFocusIndex((i) => (i + 1) % n)
    }

    let id: ReturnType<typeof setInterval> | undefined

    const start = () => {
      id = window.setInterval(advance, ROTATE_INTERVAL_MS)
    }

    const onVisibility = () => {
      if (id !== undefined) window.clearInterval(id)
      if (!document.hidden) start()
    }

    start()
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      if (id !== undefined) window.clearInterval(id)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [n, reduceMotion])

  if (reduceMotion) {
    return (
      <div className="chat-topics-grid">
        {topics.map((topic) => (
          <EmptyStateTopicCard key={topic.id} topic={topic} onPick={onPick} />
        ))}
      </div>
    )
  }

  return (
    <div
      className="stacking-viewport"
      aria-label="Sugestões em rotação automática a cada poucos segundos"
    >
      <div className="stacking-deck">
        {orderedTopics.map((topic, stackPosition) => (
          <StackingTopicCard
            key={topic.id}
            topic={topic}
            stackPosition={stackPosition}
            totalCards={n}
            motionAllowed
            onPick={onPick}
          />
        ))}
      </div>
    </div>
  )
}
