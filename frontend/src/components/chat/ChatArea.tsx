import { Message } from './Message'
import type { ChatMessage } from '../../types'

export const ChatArea = ({
  messages,
  className = '',
}: {
  messages: ChatMessage[]
  className?: string
}) => {
  return (
    <section
      className={`thin-scrollbar space-y-3 overflow-y-auto rounded-xl border border-[var(--border)] bg-[var(--bg)] p-3 ${className}`}
    >
      {messages.map((message) => (
        <Message key={message.id} message={message} />
      ))}
    </section>
  )
}
