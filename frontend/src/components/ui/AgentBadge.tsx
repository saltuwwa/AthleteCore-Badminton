import type { AgentStatus } from '../../types'

type Props = { name: string; status: AgentStatus }

export const AgentBadge = ({ name, status }: Props) => {
  const active = status === 'ACTIVE'
  const processing = status === 'PROCESSING'
  return (
    <div className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--bg3)] px-2 py-2">
      <span className="font-display text-[12px] text-[var(--text)]">{name}</span>
      <span
        className={`font-mono-ui rounded px-2 py-[2px] text-[9px] ${
          active
            ? 'bg-[rgba(200,255,95,0.12)] text-[var(--accent)]'
            : processing
              ? 'animate-pulse border border-[var(--accent)] bg-[rgba(200,255,95,0.06)] text-[var(--accent)]'
              : 'bg-[rgba(255,255,255,0.04)] text-[var(--muted)]'
        }`}
      >
        {status}
      </span>
    </div>
  )
}
