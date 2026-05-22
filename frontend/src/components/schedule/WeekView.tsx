import { EVENT_TYPE_META } from '../../types/schedule'
import type { ScheduleEvent } from '../../types/schedule'

type Props = {
  cursor: Date
  events: ScheduleEvent[]
  onPickDate: (iso: string) => void
}

const WEEK_LABELS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
const HOURS = Array.from({ length: 14 }).map((_, i) => i + 7)

const isoOf = (d: Date) => d.toISOString().slice(0, 10)
const minutesFromTime = (t: string) => {
  const [h, m] = t.split(':').map(Number)
  return h * 60 + m
}

const startOfWeek = (cursor: Date) => {
  const d = new Date(cursor)
  const offset = (d.getDay() + 6) % 7
  d.setDate(d.getDate() - offset)
  d.setHours(0, 0, 0, 0)
  return d
}

export const WeekView = ({ cursor, events, onPickDate }: Props) => {
  const start = startOfWeek(cursor)
  const days = Array.from({ length: 7 }).map((_, i) => {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    return d
  })
  const todayIso = isoOf(new Date())

  const slotHeight = 36
  const baseMinutes = HOURS[0] * 60
  const totalMinutes = HOURS.length * 60

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[rgba(13,15,23,0.65)] p-4 backdrop-blur-sm">
      <div className="grid grid-cols-[60px_repeat(7,1fr)] gap-px overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--border)]">
        <div className="bg-[rgba(13,15,23,0.85)] p-2 label-mono">Time</div>
        {days.map((d, idx) => {
          const iso = isoOf(d)
          const isToday = iso === todayIso
          return (
            <button
              type="button"
              key={iso}
              onClick={() => onPickDate(iso)}
              className={`p-2 text-left transition-colors ${
                isToday ? 'bg-[rgba(124,107,255,0.18)] text-[var(--accent)]' : 'bg-[rgba(13,15,23,0.85)] text-[var(--muted2)] hover:text-[var(--text-primary)]'
              }`}
            >
              <p className="label-mono">{WEEK_LABELS[idx]}</p>
              <p className="font-display mt-0.5 text-[16px] tabular-nums">{String(d.getDate()).padStart(2, '0')}</p>
            </button>
          )
        })}
      </div>

      <div className="relative mt-1 grid grid-cols-[60px_repeat(7,1fr)]">
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

        {days.map((d) => {
          const iso = isoOf(d)
          const dayEvents = events.filter((e) => e.date === iso)
          return (
            <div key={iso} className="relative border-l border-[var(--border)]">
              {HOURS.map((h) => (
                <div key={h} style={{ height: slotHeight }} className="border-b border-[var(--border)]" />
              ))}
              {dayEvents.map((e) => {
                const startMin = minutesFromTime(e.startTime) - baseMinutes
                const endMin = minutesFromTime(e.endTime) - baseMinutes
                const top = (startMin / 60) * slotHeight
                const height = Math.max(22, ((endMin - startMin) / 60) * slotHeight - 2)
                if (startMin < 0 || startMin > totalMinutes) return null
                const meta = EVENT_TYPE_META[e.type]
                return (
                  <div
                    key={e.id}
                    className="absolute inset-x-1 overflow-hidden rounded-lg border px-2 py-1 text-[10px] shadow-[0_4px_18px_-12px_rgba(0,0,0,0.6)]"
                    style={{
                      top,
                      height,
                      background: meta.bg,
                      borderColor: meta.border,
                      color: meta.color,
                    }}
                    title={`${e.title} · ${e.startTime}-${e.endTime}`}
                  >
                    <p className="truncate font-display text-[11px] tracking-tight">{e.title}</p>
                    <p className="truncate font-mono-ui text-[9px] tracking-wider opacity-80">{e.startTime}-{e.endTime}</p>
                  </div>
                )
              })}
            </div>
          )
        })}
      </div>
    </div>
  )
}
