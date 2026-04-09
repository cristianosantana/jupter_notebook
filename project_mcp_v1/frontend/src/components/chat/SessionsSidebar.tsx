import type { SessionRow } from '../../chat/types'
import { shortId, formatWhen } from '../../chat/format'
import { PipelineStatusBlock } from '../assistant/PipelineStatusBlock'

export function SessionsSidebar({
  onNewConversation,
  sessionsLoading,
  persistenceEnabled,
  sessions,
  sessionId,
  sessionDetailLoading,
  onSelectSession,
  traceRunId,
  agentUsed,
  pipelineStep,
}: {
  onNewConversation: () => void
  sessionsLoading: boolean
  persistenceEnabled: boolean
  sessions: SessionRow[]
  sessionId: string | null
  sessionDetailLoading: string | null
  onSelectSession: (row: SessionRow) => void
  traceRunId: string | null
  agentUsed: string | null
  pipelineStep: number
}) {
  return (
    <aside className="chat-sidebar">
      <header className="chat-sidebar-header">
        <span className="text-2xl" aria-hidden>
          🤖
        </span>
        <h1 className="chat-sidebar-title">SmartChat</h1>
      </header>

      <div className="p-3">
        <button
          type="button"
          onClick={onNewConversation}
          className="chat-btn-new-chat"
        >
          + Nova conversa
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col px-3 pb-2">
        <div className="chat-sidebar-section-label">
          <span className="font-mono text-[10px] text-slate-500">&lt;/&gt;</span>
          Histórico de conversas
        </div>
        <div className="chat-sidebar-session-scroll">
          {sessionsLoading ? (
            <PipelineStatusBlock stepIndex={pipelineStep} compact />
          ) : !persistenceEnabled ? (
            <p className="p-3 text-xs text-slate-500">
              PostgreSQL inactivo — sem histórico persistido.
            </p>
          ) : sessions.length === 0 ? (
            <p className="p-3 text-xs text-slate-500">Nenhuma sessão ainda.</p>
          ) : (
            <ul className="divide-y divide-slate-800">
              {sessions.map((s) => {
                const active = s.session_id === sessionId
                const busy = sessionDetailLoading === s.session_id
                return (
                  <li key={s.session_id}>
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void onSelectSession(s)}
                      className={`chat-sidebar-session-btn ${active ? 'chat-sidebar-session-btn-active' : ''}`}
                    >
                      <div className="font-mono text-emerald-400">
                        {shortId(s.session_id)}
                        {busy ? ' …' : ''}
                      </div>
                      <div className="mt-0.5 text-violet-300">
                        {s.current_agent}
                      </div>
                      <div className="mt-0.5 text-slate-500">
                        {formatWhen(s.last_active_at)}
                      </div>
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </div>

      <div className="mt-auto space-y-2 border-t border-slate-800 p-3">
        <div className="chat-sidebar-footer-panel">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Sessão activa
          </div>
          <div className="mt-1 font-mono text-xs text-emerald-400">
            {shortId(sessionId)}
          </div>
        </div>
        <div className="chat-sidebar-footer-panel">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Trace run
          </div>
          <div className="mt-1 font-mono text-xs text-sky-300 break-all">
            {traceRunId ?? 'Aguardando primeira msg…'}
          </div>
        </div>
        <div className="chat-sidebar-footer-panel">
          <div className="text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Agente actual
          </div>
          <div className="mt-1 font-mono text-xs text-violet-300">
            {agentUsed ? agentUsed : 'Nenhum (Maestro)'}
          </div>
        </div>
        <p className="text-[10px] leading-snug text-slate-600">
          O <span className="font-mono">session_id</span>,{' '}
          <span className="font-mono">target_agent</span> (eco do último{' '}
          <span className="font-mono">agent_used</span>) e{' '}
          <span className="font-mono">user_id</span> opcional são enviados no
          próximo pedido.
        </p>
      </div>
    </aside>
  )
}
