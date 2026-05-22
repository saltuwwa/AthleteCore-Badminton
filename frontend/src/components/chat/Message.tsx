import { motion } from 'framer-motion'
import type { ChatMessage } from '../../types'
import { AnalysisCard } from './AnalysisCard'

export const Message = ({ message }: { message: ChatMessage }) => {
  const user = message.role === 'user'
  const draft = message.draft

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="flex gap-2"
    >
      <div
        className={`flex h-7 w-7 items-center justify-center rounded-md text-[11px] font-semibold ${
          user ? 'bg-[rgba(95,159,255,0.15)] text-[var(--accent2)]' : 'bg-[rgba(200,255,95,0.1)] text-[var(--accent)]'
        }`}
      >
        {user ? 'AK' : 'AC'}
      </div>
      <div className="max-w-[85%]">
        <p className="font-mono-ui text-[9px] text-[var(--muted)]">
          {message.agentLabel} - {message.timestamp}
        </p>
        {message.processing ? (
          <div className="mt-1 inline-flex items-center gap-1 rounded-[10px] border border-[var(--border)] bg-[var(--bg2)] px-3 py-2">
            <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-[var(--accent)]" />
            <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-[var(--accent)] [animation-delay:0.2s]" />
            <span className="pulse-dot h-1.5 w-1.5 rounded-full bg-[var(--accent)] [animation-delay:0.4s]" />
          </div>
        ) : (
          <div
            className={`mt-1 rounded-[10px] px-3 py-2 ${
              draft
                ? 'rounded-tr-none border border-dashed border-[var(--accent2)] bg-[rgba(95,159,255,0.04)]'
                : user
                  ? 'rounded-tr-none bg-[rgba(95,159,255,0.06)]'
                  : 'rounded-tl-none border border-[var(--border)] bg-[var(--bg2)]'
            }`}
          >
            {message.content}
            {draft ? (
              <p className="mt-2 font-mono-ui text-[9px] text-[var(--accent2)]">
                Проверь текст и нажми «Отправить →»
              </p>
            ) : null}
          </div>
        )}
        {message.analysis ? (
          <AnalysisCard level={message.analysis.level} text={message.analysis.text} pattern={message.analysis.pattern} />
        ) : null}
      </div>
    </motion.div>
  )
}
