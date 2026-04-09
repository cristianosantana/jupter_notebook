import type { RefObject, SubmitEvent } from 'react'
import { SendIcon } from './SendIcon'

export function ChatComposer({
  input,
  setInput,
  loading,
  sendMessage,
  chatInputRef,
  error,
  onCancelChat,
}: {
  input: string
  setInput: (v: string) => void
  loading: boolean
  sendMessage: (e?: SubmitEvent<HTMLFormElement>) => void | Promise<void>
  chatInputRef: RefObject<HTMLTextAreaElement | null>
  error: string | null
  onCancelChat: () => void
}) {
  return (
    <>
      {error ? <div className="chat-composer-error">{error}</div> : null}
      <form onSubmit={sendMessage} className="chat-composer-form">
        <textarea
          ref={chatInputRef}
          rows={1}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              if (!loading && input.trim()) void sendMessage()
            }
          }}
          placeholder="Mensagem…"
          disabled={loading}
          className="chat-composer-textarea"
        />
        <div className="chat-composer-actions">
          {loading ? (
            <button
              type="button"
              className="chat-btn-cancel"
              onClick={onCancelChat}
            >
              Cancelar
            </button>
          ) : null}
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="chat-btn-send-sm"
            aria-label="Enviar"
          >
            <SendIcon />
          </button>
        </div>
      </form>
    </>
  )
}
