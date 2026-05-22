import type { RiskLevel } from '../../types'

export const ErrorTag = ({ level }: { level: RiskLevel }) => {
  const style =
    level === 'HIGH'
      ? 'bg-[rgba(255,127,95,0.2)] text-[var(--accent3)]'
      : level === 'MED'
        ? 'bg-[rgba(255,200,60,0.18)] text-[var(--amber)]'
        : 'bg-[rgba(200,255,95,0.18)] text-[var(--accent)]'
  return <span className={`font-mono-ui rounded px-2 py-[3px] text-[9px] ${style}`}>{level}</span>
}
