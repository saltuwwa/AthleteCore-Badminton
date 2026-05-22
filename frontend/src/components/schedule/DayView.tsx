import { EVENT_TYPE_META } from '../../types/schedule'
import type { ScheduleEvent } from '../../types/schedule'

type Props = {
  cursor: Date
  events: ScheduleEvent[]
}

const HOURS = Array.from({ length: 16 }).map((_, i) => i + 6)
const isoOf = (d: Date) => d.toISOString().slice(0, 10)
const minutesFromTime = (t: string) => {
  const [h, m] = t.split(':').map(Number)
  return h * 60 + m
}

export const DayView = ({ cursor, events }: Props) => {
  const iso = isoOf(cursor)
  const day = events.filter((e) => e.date === iso)
  const slotHeight = 48
  const baseMinutes = HOURS[0] * 60
  const totalMinutes = HOURS.length * 60

  return (
    <div className="grid grid-cols-[1fr_340px] gap-3">
      <div className="rounded-2xl border border-[var(--border)] bg-[rgba(13,15,23,0.65)] p-5 backdrop-blur-sm">
        <div className="flex items-baseline justify-between">
          <p className="font-display text-[18px] capitalize tracking-tight">
            {cursor.toLocaleDateString('ru-RU', { weekday: 'long', day: '2-digit', month: 'long' })}
          </p>
          <p className="label-mono">events · {String(day.length).padStart(2, '0')}</p>
        </div>
        <div className="relative mt-4 grid grid-cols-[60px_1fr]">
          <div>
            {HOURS.map((h) => (
              <div
                key={h}
                style={{ height: slotHeight }}
                className="flex items-start border-b border-[var(--border)] px-2 pt-1 font-mono-ui text-[10px] tracking-wider text-[var(--muted)]"
              >
                {String(h).padStart(2, '0')}:00
              </div>
            ))}
          </div>
          <div className="relative border-l border-[var(--border)]">
            {HOURS.map((h) => (
              <div key={h} style={{ height: slotHeight }} className="border-b border-[var(--border)]" />
            ))}
            {day.map((e) => {
              const startMin = minutesFromTime(e.startTime) - baseMinutes
              const endMin = minutesFromTime(e.endTime) - baseMinutes
              if (startMin < 0 || startMin > totalMinutes) return null
              const top = (startMin / 60) * slotHeight
              const height = Math.max(36, ((endMin - startMin) / 60) * slotHeight - 2)
              const meta = EVENT_TYPE_META[e.type]
              return (
                <div
                  key={e.id}
                  className="absolute inset-x-2 rounded-xl border px-3 py-2 shadow-[0_8px_24px_-16px_rgba(0,0,0,0.6)]"
                  style={{ top, height, background: meta.bg, borderColor: meta.border, color: meta.color }}
                >
                  <p className="font-display text-[13px] tracking-tight">{e.title}</p>
                  <p className="font-mono-ui mt-0.5 text-[10px] tracking-wider opacity-80">
                    {e.startTime} → {e.endTime} · {meta.label}
                  </p>
                  {e.aiAdded ? <span className="label-mono mt-1 inline-block text-[var(--accent)]">↻ AI</span> : null}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      <aside className="rounded-2xl border border-[var(--border)] bg-[rgba(13,15,23,0.65)] p-4 backdrop-blur-sm">
        <div className="mb-3 flex items-center justify-between">
          <p className="font-display text-[14px] tracking-tight">События дня</p>
          <span className="label-mono">{String(day.length).padStart(2, '0')}</span>
        </div>
        {day.length === 0 ? (
          <div className="rounded-xl border border-dashed border-[var(--border)] p-4">
            <p className="text-[12px] text-[var(--muted2)]">
              На этот день событий нет. Можно добавить вручную или попросить агента.
            </p>
          </div>
        ) : (
          <ul className="space-y-2">
            {day
              .slice()
              .sort((a, b) => a.startTime.localeCompare(b.startTime))
              .map((e) => {
                const meta = EVENT_TYPE_META[e.type]
                return (
                  <li
                    key={e.id}
                    className="rounded-xl border border-[var(--border)] bg-[rgba(20,24,38,0.55)] p-3"
                  >
                    <div className="flex items-baseline justify-between">
                      <p className="font-mono-ui text-[10px] tracking-wider text-[var(--muted)]">
                        {e.startTime} → {e.endTime}
                      </p>
                      {e.aiAdded ? <span className="label-mono text-[var(--accent)]">AI</span> : null}
                    </div>
                    <p className="font-display mt-1 text-[13px] tracking-tight">{e.title}</p>
                    <span
                      className="mt-2 inline-block rounded-full px-2 py-0.5 font-mono-ui text-[10px] tracking-wider"
                      style={{ background: meta.bg, color: meta.color }}
                    >
                      {meta.label}
                    </span>
                  </li>
                )
              })}
          </ul>
        )}
      </aside>
    </div>
  )
}
