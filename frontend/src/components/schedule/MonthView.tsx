import { EVENT_TYPE_META } from '../../types/schedule'
import type { ScheduleEvent } from '../../types/schedule'

type Props = {
  cursor: Date
  events: ScheduleEvent[]
  onPickDate: (iso: string) => void
}

const WEEK_LABELS = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']

const isoOf = (d: Date) => d.toISOString().slice(0, 10)

const buildGrid = (cursor: Date) => {
  const first = new Date(cursor.getFullYear(), cursor.getMonth(), 1)
  const startOffset = (first.getDay() + 6) % 7
  const start = new Date(first)
  start.setDate(first.getDate() - startOffset)

  return Array.from({ length: 42 }).map((_, i) => {
    const d = new Date(start)
    d.setDate(start.getDate() + i)
    return d
  })
}

export const MonthView = ({ cursor, events, onPickDate }: Props) => {
  const grid = buildGrid(cursor)
  const todayIso = isoOf(new Date())
  const month = cursor.getMonth()

  const eventsByDay = events.reduce<Record<string, ScheduleEvent[]>>((acc, e) => {
    acc[e.date] ??= []
    acc[e.date].push(e)
    return acc
  }, {})

  return (
    <div className="rounded-2xl border border-[var(--border)] bg-[rgba(13,15,23,0.65)] p-4 backdrop-blur-sm">
      <div className="grid grid-cols-7 gap-1 pb-3 text-center">
        {WEEK_LABELS.map((l) => (
          <div key={l} className="label-mono">{l}</div>
        ))}
      </div>
      <div className="grid grid-cols-7 gap-1">
        {grid.map((d) => {
          const iso = isoOf(d)
          const dayEvents = eventsByDay[iso] ?? []
          const isOtherMonth = d.getMonth() !== month
          const isToday = iso === todayIso
          return (
            <button
              type="button"
              key={iso}
              onClick={() => onPickDate(iso)}
              className={`group flex min-h-[88px] flex-col items-stretch gap-1.5 rounded-xl border p-2 text-left transition-all ${
                isToday
                  ? 'border-[var(--accent)] bg-[rgba(124,107,255,0.12)] shadow-[inset_0_0_0_1px_rgba(124,107,255,0.25)]'
                  : 'border-[var(--border)] bg-[rgba(20,24,38,0.45)] hover:border-[var(--border-strong)] hover:bg-[rgba(28,33,52,0.6)]'
              } ${isOtherMonth ? 'opacity-30' : ''}`}
            >
              <div className="flex items-center justify-between">
                <span
                  className={`font-display text-[14px] tabular-nums ${
                    isToday ? 'text-[var(--accent)]' : 'text-[var(--text-soft)]'
                  }`}
                >
                  {String(d.getDate()).padStart(2, '0')}
                </span>
                {dayEvents.length > 0 ? (
                  <span className="font-mono-ui text-[9px] tracking-wider text-[var(--muted)]">
                    {String(dayEvents.length).padStart(2, '0')}
                  </span>
                ) : null}
              </div>
              <div className="flex flex-col gap-1">
                {dayEvents.slice(0, 3).map((e) => {
                  const meta = EVENT_TYPE_META[e.type]
                  return (
                    <span
                      key={e.id}
                      className="truncate rounded-md border px-1.5 py-0.5 text-[9.5px]"
                      style={{ background: meta.bg, color: meta.color, borderColor: meta.border }}
                      title={e.title}
                    >
                      <span className="font-mono-ui tracking-wider opacity-80">{e.startTime}</span>{' '}
                      <span className="font-display">{e.title}</span>
                    </span>
                  )
                })}
                {dayEvents.length > 3 ? (
                  <span className="font-mono-ui text-[9px] text-[var(--muted)]">+{dayEvents.length - 3}</span>
                ) : null}
              </div>
            </button>
          )
        })}
      </div>
    </div>
  )
}
