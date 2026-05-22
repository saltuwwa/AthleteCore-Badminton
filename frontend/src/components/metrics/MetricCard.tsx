export const MetricCard = ({
  label,
  value,
  delta,
  tone,
}: {
  label: string
  value: string
  delta: string
  tone: 'accent' | 'warn' | 'amber'
}) => {
  const valueColor =
    tone === 'accent' ? 'var(--accent)' : tone === 'warn' ? 'var(--accent3)' : 'var(--amber)'
  return (
    <article className="rounded-xl border border-[var(--border)] bg-[var(--bg2)] p-3">
      <p className="font-mono-ui text-[10px] text-[var(--muted)]">{label}</p>
      <p className="font-display mt-1 text-[24px] font-bold" style={{ color: valueColor }}>
        {value}
      </p>
      <p className="font-mono-ui text-[10px] text-[var(--muted)]">{delta}</p>
    </article>
  )
}
