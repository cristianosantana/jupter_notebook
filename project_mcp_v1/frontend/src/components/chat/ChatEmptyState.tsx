import type { RefObject, SubmitEvent } from 'react'
import {
  EmptyStateTopicDisplay,
  type EmptyStateTopicDisplayMode,
} from '../emptyState/EmptyStateTopicDisplay'
import {
  EMPTY_STATE_TOPICS,
  type EmptyStateTopic,
} from '../emptyState/emptyStateTopics'
import { SendIcon } from './SendIcon'

/** Uma linha: `stack` (pilha 3D) ou `carousel` (slides + pontos). */
const EMPTY_STATE_TOPICS_MODE: EmptyStateTopicDisplayMode = 'carousel'

export function ChatEmptyState({
  error,
  input,
  setInput,
  loading,
  sendMessage,
  chatInputRef,
  onPickTopic,
  onCancelChat,
}: {
  error: string | null
  input: string
  setInput: (v: string) => void
  loading: boolean
  sendMessage: (e?: SubmitEvent<HTMLFormElement>) => void | Promise<void>
  chatInputRef: RefObject<HTMLTextAreaElement | null>
  onPickTopic: (t: EmptyStateTopic) => void
  onCancelChat: () => void
}) {
  return (
    <div className="chat-empty-outer">
      <div className="chat-empty-hero">
        <div className="chat-empty-hero-inner">
          <header className="text-center sm:text-left">
            <div className="chat-empty-header-row">
              <span className="text-3xl leading-none" aria-hidden>
                ✦
              </span>
              <h2 className="chat-empty-title">Olá!</h2>
            </div>
            {/* <p className="chat-empty-subtitle">Por onde começamos?</p> */}
            {/* <p className="chat-empty-desc">
              Assistente de análise da rede — OS, faturamento, vendedores e
              concessionárias. A primeira mensagem cria um{' '}
              <code className="chat-empty-code">session_id</code> (PostgreSQL
              activo) e o contexto mantém-se nas mensagens seguintes.
            </p> */}
          </header>

          {error ? <div className="chat-empty-error">{error}</div> : null}

          <form onSubmit={sendMessage} className="chat-empty-form">
            <textarea
              ref={chatInputRef}
              rows={4}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  if (!loading && input.trim()) void sendMessage()
                }
              }}
              placeholder="Peça uma análise, cole contexto ou escolha um cartão abaixo…"
              disabled={loading}
              className="chat-empty-textarea"
            />
            <div className="chat-empty-form-footer">
              <span className="chat-empty-hint-desktop">
                Enter para enviar · Shift+Enter nova linha
              </span>
              <span className="chat-empty-hint-mobile">Enter envia</span>
              <div className="chat-empty-form-actions-end">
                {loading ? (
                  <button
                    type="button"
                    className="chat-btn-cancel-lg"
                    onClick={onCancelChat}
                  >
                    Cancelar
                  </button>
                ) : null}
                <button
                  type="submit"
                  disabled={loading || !input.trim()}
                  className="chat-btn-send-lg"
                  aria-label="Enviar"
                >
                  <SendIcon />
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>

      <div className="chat-topics-section-wrap">
        <p className="chat-topics-section-title">
          Perguntas que esta solução responde — toque para preencher o campo
          acima
        </p>
        <EmptyStateTopicDisplay
          mode={EMPTY_STATE_TOPICS_MODE}
          topics={EMPTY_STATE_TOPICS}
          onPick={onPickTopic}
        />
      </div>
    </div>
  )
}
