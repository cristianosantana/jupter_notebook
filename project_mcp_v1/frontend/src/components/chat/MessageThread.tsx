import type { ChatMessage } from '../../chat/types'
import { StructuredAssistantMessage } from '../assistant/StructuredAssistantMessage'
import { PipelineStatusBlock } from '../assistant/PipelineStatusBlock'

export function MessageThread({
  messages,
  loading,
  pipelineStep,
}: {
  messages: ChatMessage[]
  loading: boolean
  pipelineStep: number
}) {
  return (
    <div className="msg-thread-wrap">
      {messages.map((msg, i) => (
        <div
          key={`${i}-${msg.role}`}
          className={`msg-row ${msg.role === 'user' ? 'msg-row-user' : 'msg-row-assistant'}`}
        >
          <div
            className={
              msg.role === 'user' ? 'msg-bubble-user' : 'msg-bubble-assistant'
            }
          >
            {msg.role === 'user' ? (
              <span className="block whitespace-pre-wrap break-words">
                {msg.content}
              </span>
            ) : (
              <StructuredAssistantMessage
                content={msg.content}
                contentBlocks={msg.contentBlocks}
              />
            )}
          </div>
        </div>
      ))}
      {loading ? (
        <PipelineStatusBlock stepIndex={pipelineStep} />
      ) : null}
    </div>
  )
}
