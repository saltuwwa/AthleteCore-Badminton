import { useEffect, useState } from 'react'

type BwfResult = {
  rank: number
  category: 'WS' | 'MS' | 'MD' | 'WD' | 'XD'
  points: number
}

export const BWFRankCard = () => {
  const [loading, setLoading] = useState(true)
  const [data, setData] = useState<BwfResult | null>(null)

  useEffect(() => {
    const timer = setTimeout(() => {
      setData({ rank: 543, category: 'WS', points: 12420 })
      setLoading(false)
    }, 900)
    return () => clearTimeout(timer)
  }, [])

  const progress = data ? Math.max(0, Math.min(100, ((1000 - data.rank) / 500) * 100)) : 0

  return (
    <article className="crosshair-corner relative rounded-2xl border border-[var(--border)] bg-[rgba(20,24,38,0.7)] p-5">
      <div className="flex items-center justify-between">
        <p className="label-mono">BWF Live Ranking</p>
        <span className="font-mono-ui text-[10px] tracking-wider text-[var(--muted2)]">scraped · 24h cache</span>
      </div>
      {loading ? (
        <div className="mt-4 space-y-3">
          <div className="h-9 animate-pulse rounded bg-[var(--bg4)]" />
          <div className="h-4 w-2/3 animate-pulse rounded bg-[var(--bg4)]" />
          <div className="h-2 animate-pulse rounded bg-[var(--bg4)]" />
        </div>
      ) : (
        <div className="mt-4">
          <div className="flex items-baseline justify-between">
            <p className="hero-number text-[44px]">
              <span className="text-[var(--muted)]">#</span>{data?.rank}
            </p>
            <span className="rounded-full bg-[rgba(124,107,255,0.18)] px-3 py-1 font-mono-ui text-[11px] tracking-wider text-[var(--accent-strong)]">
              {data?.category}
            </span>
          </div>
          <p className="label-mono mt-2">{data?.points.toLocaleString('ru-RU')} очков</p>
          <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-[var(--bg4)]">
            <div className="h-full bg-gradient-to-r from-[var(--accent)] to-[var(--accent2)]" style={{ width: `${progress}%` }} />
          </div>
          <p className="label-mono mt-2 text-right">прогресс к Top 500</p>
        </div>
      )}
    </article>
  )
}
