import type { ReactNode } from 'react'

export function ChatLayout({
  emptyMain,
  sidebar,
  children,
}: {
  emptyMain: boolean
  sidebar: ReactNode
  children: ReactNode
}) {
  return (
    <div className="chat-app-shell">
      {sidebar}
      <main
        className={`chat-main flex min-h-0 flex-1 flex-col ${emptyMain ? 'chat-main-empty-bg' : 'chat-main-messages-bg'}`}
      >
        {children}
      </main>
    </div>
  )
}
