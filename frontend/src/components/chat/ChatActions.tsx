import { Link } from 'react-router-dom'
import type { ChatAction } from '../../types'

export const ChatActions = ({
  actions,
  onPrefill,
}: {
  actions: ChatAction[]
  onPrefill?: (text: string) => void
}) => {
  if (!actions.length) return null
  return (
    <div className="mt-2 flex flex-wrap gap-2">
      {actions.map((a) =>
        a.href ? (
          <Link
            key={a.id}
            to={a.href}
            className="rounded-full border border-[var(--border)] bg-[var(--bg3)] px-3 py-1 text-[10px] text-[var(--accent2)] hover:border-[var(--accent2)]"
          >
            {a.label}
          </Link>
        ) : (
          <button
            key={a.id}
            type="button"
            onClick={() => a.prefill && onPrefill?.(a.prefill)}
            className="rounded-full border border-[var(--border)] bg-[var(--bg3)] px-3 py-1 text-[10px] text-[var(--accent2)] hover:border-[var(--accent2)]"
          >
            {a.label}
          </button>
        ),
      )}
    </div>
  )
}
