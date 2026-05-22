type Props = {
  values: { label: string; value: number; color?: string }[]
  max?: number
  height?: number
}

export const Bars = ({ values, max, height = 110 }: Props) => {
  const safeMax = max ?? Math.max(...values.map((v) => v.value), 1)
  return (
    <div className="flex items-end gap-2" style={{ height }}>
      {values.map((v) => {
        const h = Math.max(4, (v.value / safeMax) * (height - 18))
        return (
          <div key={v.label} className="flex flex-1 flex-col items-center gap-1">
            <div
              className="w-full rounded-md"
              style={{ height: h, background: v.color ?? 'rgba(124,107,255,0.55)' }}
            />
            <span className="text-[9px] text-[var(--muted)]">{v.label}</span>
          </div>
        )
      })}
    </div>
  )
}
