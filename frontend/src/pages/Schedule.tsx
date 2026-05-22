import { motion } from 'framer-motion'
import { useMemo, useState } from 'react'
import { PageTabs } from '../components/layout/PageTabs'
import { SignalStrip } from '../components/layout/SignalStrip'
import { AddEventModal } from '../components/schedule/AddEventModal'
import { DayView } from '../components/schedule/DayView'
import { MonthView } from '../components/schedule/MonthView'
import { WeekView } from '../components/schedule/WeekView'
import { useScheduleEvents } from '../hooks/useScheduleEvents'
import type { ScheduleView } from '../types/schedule'

const VIEW_LABELS: Record<ScheduleView, string> = {
  month: 'Месяц',
  week: 'Неделя',
  day: 'День',
}

const titleFor = (view: ScheduleView, cursor: Date) => {
  if (view === 'month') return cursor.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })
  if (view === 'day') return cursor.toLocaleDateString('ru-RU', { weekday: 'long', day: '2-digit', month: 'long' })
  const start = new Date(cursor)
  const offset = (start.getDay() + 6) % 7
  start.setDate(start.getDate() - offset)
  const end = new Date(start)
  end.setDate(start.getDate() + 6)
  const fmt = (d: Date) => d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short' })
  return `${fmt(start)} - ${fmt(end)}`
}

const container = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
}
const item = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] as const } },
}

export const Schedule = () => {
  const [view, setView] = useState<ScheduleView>('week')
  const [cursor, setCursor] = useState(() => new Date())
  const [modalOpen, setModalOpen] = useState(false)
  const [modalDate, setModalDate] = useState<string | undefined>()
  const { events, addEvent } = useScheduleEvents()

  const shift = (delta: number) => {
    const next = new Date(cursor)
    if (view === 'month') next.setMonth(next.getMonth() + delta)
    else if (view === 'week') next.setDate(next.getDate() + 7 * delta)
    else next.setDate(next.getDate() + delta)
    setCursor(next)
  }

  const stats = useMemo(() => {
    const total = events.length
    const matches = events.filter((e) => e.type === 'MATCH').length
    const ai = events.filter((e) => e.aiAdded).length
    return { total, matches, ai }
  }, [events])

  const openAddDialog = (iso?: string) => {
    setModalDate(iso ?? cursor.toISOString().slice(0, 10))
    setModalOpen(true)
  }

  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="visible"
      className="thin-scrollbar flex h-full flex-col overflow-y-auto"
    >
      <div className="flex items-start justify-between gap-4 px-8 pb-4 pt-7">
        <motion.div variants={item}>
          <p className="label-mono">Operational planner</p>
          <h1 className="font-display mt-2 text-[32px] leading-[0.95] tracking-tight">
            Расписание <span className="text-[var(--accent)]">/ AI draft</span>
          </h1>
          <p className="mt-2 max-w-lg text-[12.5px] text-[var(--muted2)]">
            Планировщик автоматически балансирует тренировки, восстановление и матчи на 4 недели вперёд.
          </p>
        </motion.div>
        <motion.div variants={item}>
          <PageTabs />
        </motion.div>
      </div>

      <div className="diagonal-divider mx-8 h-px" />
      <SignalStrip
        title="Planner Sync"
        items={[
          { label: 'NEXT MATCH', value: 'THU 17:00', tone: 'alert' },
          { label: 'AI ADDED', value: `${stats.ai} blocks`, tone: 'accent' },
          { label: 'RECOVERY GAPS', value: '1 found', tone: 'alert' },
          { label: 'TRAINING LOAD', value: '74%', tone: 'good' },
          { label: 'CONFIRMATION', value: 'HITL enabled', tone: 'neutral' },
        ]}
      />

      <motion.div variants={item} className="flex flex-wrap items-center justify-between gap-3 px-8 pt-6">
        <div className="flex items-center gap-1">
          <button type="button" onClick={() => shift(-1)} className="h-9 w-9 rounded-full border border-[var(--border)] bg-[var(--bg2)] text-[14px] text-[var(--muted2)] hover:text-[var(--text-primary)]">‹</button>
          <button type="button" onClick={() => setCursor(new Date())} className="rounded-full border border-[var(--border)] bg-[var(--bg2)] px-4 py-1.5 font-display text-[12px] text-[var(--text-primary)]">Сегодня</button>
          <button type="button" onClick={() => shift(1)} className="h-9 w-9 rounded-full border border-[var(--border)] bg-[var(--bg2)] text-[14px] text-[var(--muted2)] hover:text-[var(--text-primary)]">›</button>
          <p className="font-display ml-3 text-[18px] capitalize tracking-tight">{titleFor(view, cursor)}</p>
        </div>

        <div className="flex items-center gap-2">
          <div className="flex rounded-full border border-[var(--border)] bg-[var(--surface-1)] p-1 backdrop-blur-md">
            {(['month', 'week', 'day'] as ScheduleView[]).map((v) => (
              <button
                key={v}
                type="button"
                onClick={() => setView(v)}
                className={`rounded-full px-4 py-1.5 font-display text-[12px] transition-colors ${
                  view === v ? 'bg-[var(--accent2)] text-[var(--bg-deep)]' : 'text-[var(--muted2)] hover:text-[var(--text-primary)]'
                }`}
              >
                {VIEW_LABELS[v]}
              </button>
            ))}
          </div>
          <button
            type="button"
            onClick={() => openAddDialog()}
            className="rounded-full bg-[var(--accent)] px-4 py-2 font-display text-[12px] font-semibold tracking-wide text-white"
          >
            + Добавить событие
          </button>
        </div>
      </motion.div>

      <motion.section variants={item} className="grid grid-cols-3 gap-3 px-8 pt-5">
        {[
          { label: 'Всего событий', value: stats.total, color: 'var(--text-primary)' },
          { label: 'Матчи / турниры', value: stats.matches, color: 'var(--accent3)' },
          { label: 'Добавлено AI', value: stats.ai, color: 'var(--accent)' },
        ].map((s) => (
          <article
            key={s.label}
            className="crosshair-corner relative rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm"
          >
            <p className="label-mono">{s.label}</p>
            <p className="hero-number mt-3 text-[56px]" style={{ color: s.color }}>
              {String(s.value).padStart(2, '0')}
            </p>
          </article>
        ))}
      </motion.section>

      <motion.section variants={item} className="px-8 pb-8 pt-5">
        {view === 'month' ? (
          <MonthView cursor={cursor} events={events} onPickDate={(iso) => { setCursor(new Date(iso)); setView('day') }} />
        ) : null}
        {view === 'week' ? (
          <WeekView cursor={cursor} events={events} onPickDate={(iso) => { setCursor(new Date(iso)); setView('day') }} />
        ) : null}
        {view === 'day' ? <DayView cursor={cursor} events={events} /> : null}
      </motion.section>

      <AddEventModal
        isOpen={modalOpen}
        initialDate={modalDate}
        onClose={() => setModalOpen(false)}
        onSubmit={addEvent}
      />
    </motion.div>
  )
}
