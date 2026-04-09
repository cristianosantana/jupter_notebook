import type { EmptyStateTopic } from './emptyStateTopics'
import { topicCardPreview } from './emptyStateTopics'

export function EmptyStateTopicCard({
  topic,
  onPick,
}: {
  topic: EmptyStateTopic
  onPick: (t: EmptyStateTopic) => void
}) {
  return (
    <button
      type="button"
      onClick={() => onPick(topic)}
      className="topic-card-btn"
    >
      <div className="flex items-start gap-3">
        <span className="topic-card-icon" aria-hidden>
          {topic.icon}
        </span>
        <div className="min-w-0 flex-1">
          <span className="topic-card-title">{topic.title}</span>
          <p className="topic-card-preview">{topicCardPreview(topic.text)}</p>
        </div>
      </div>
    </button>
  )
}
