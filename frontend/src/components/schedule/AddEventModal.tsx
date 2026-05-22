import { AnimatePresence, motion } from 'framer-motion'
import { useEffect, useState } from 'react'
import type { EventType, ScheduleEvent } from '../../types/schedule'
import { EVENT_TYPE_META } from '../../types/schedule'

type Props = {
  isOpen: boolean
  initialDate?: string
  onClose: () => void
  onSubmit: (event: Omit<ScheduleEvent, 'id'>) => void
}

const types: EventType[] = ['TRAINING', 'MATCH', 'RECOVERY', 'STUDY', 'GYM', 'OTHER']

export const AddEventModal = ({ isOpen, initialDate, onClose, onSubmit }: Props) => {
  const [date, setDate] = useState(initialDate ?? new Date().toISOString().slice(0, 10))
  const [startTime, setStartTime] = useState('09:00')
  const [endTime, setEndTime] = useState('10:00')
  const [title, setTitle] = useState('')
  const [type, setType] = useState<EventType>('TRAINING')
  const [intensity, setIntensity] = useState(3)
  const [notes, setNotes] = useState('')

  useEffect(() => {
    if (isOpen && initialDate) setDate(initialDate)
  }, [isOpen, initialDate])

  const submit = () => {
    if (!title.trim()) return
    onSubmit({ date, startTime, endTime, title: title.trim(), type, intensity, notes: notes.trim() || undefined })
    setTitle('')
    setNotes('')
    onClose()
  }

  return (
    <AnimatePresence>
      {isOpen ? (
        <>
          <motion.button
            type="button"
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/60"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
          <motion.div
            className="fixed left-1/2 top-1/2 z-50 w-[min(520px,92vw)] -translate-x-1/2 -translate-y-1/2 rounded-2xl border border-[var(--border)] bg-[var(--bg2)] p-5"
            initial={{ opacity: 0, y: 12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.97 }}
            transition={{ type: 'spring', damping: 26, stiffness: 280 }}
          >
            <div className="mb-4 flex items-center justify-between">
              <h3 className="font-display text-[16px]">Новое событие</h3>
              <button type="button" onClick={onClose} className="rounded-md border border-[var(--border)] px-2 py-1 text-[11px] text-[var(--muted2)]">
                Esc
              </button>
            </div>

            <div className="space-y-3">
              <label className="block">
                <span className="text-[11px] text-[var(--muted2)]">Название</span>
                <input
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                  placeholder="Например: Спарринг с тренером"
                  className="mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--bg3)] px-3 py-2 text-[13px] outline-none focus:border-[var(--accent)]"
                />
              </label>

              <div className="grid grid-cols-3 gap-2">
                <label>
                  <span className="text-[11px] text-[var(--muted2)]">Дата</span>
                  <input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--bg3)] px-3 py-2 text-[13px] outline-none focus:border-[var(--accent)]" />
                </label>
                <label>
                  <span className="text-[11px] text-[var(--muted2)]">Начало</span>
                  <input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} className="mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--bg3)] px-3 py-2 text-[13px] outline-none focus:border-[var(--accent)]" />
                </label>
                <label>
                  <span className="text-[11px] text-[var(--muted2)]">Конец</span>
                  <input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} className="mt-1 w-full rounded-lg border border-[var(--border)] bg-[var(--bg3)] px-3 py-2 text-[13px] outline-none focus:border-[var(--accent)]" />
                </label>
              </div>

              <div>
                <span className="text-[11px] text-[var(--muted2)]">Тип</span>
                <div className="mt-1 flex flex-wrap gap-2">
                  {types.map((t) => {
                    const meta = EVENT_TYPE_META[t]
                    const active = type === t
                    return (
                      <button
                        type="button"
                        key={t}
                        onClick={() => setType(t)}
                        className="rounded-md border px-2 py-1 text-[11px]"
                        style={{
                          background: active ? meta.bg : 'var(--bg3)',
                          borderColor: active ? meta.border : 'var(--border)',
                          color: active ? meta.color : 'var(--muted2)',
                        }}
                      >
                        {meta.label}
                      </button>
                    )
                  })}
                </div>
              </div>

              <label className="block">
                <span className="text-[11px] text-[var(--muted2)]">Интенсивность ({intensity}/5)</span>
                <input
                  type="range"
                  min={1}
                  max={5}
                  value={intensity}
                  onChange={(e) => setIntensity(Number(e.target.value))}
                  className="mt-2 w-full accent-[var(--accent)]"
                />
              </label>

              <label className="block">
                <span className="text-[11px] text-[var(--muted2)]">Заметки</span>
                <textarea
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  rows={2}
                  className="mt-1 w-full resize-none rounded-lg border border-[var(--border)] bg-[var(--bg3)] px-3 py-2 text-[13px] outline-none focus:border-[var(--accent)]"
                />
              </label>
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <button type="button" onClick={onClose} className="rounded-lg border border-[var(--border)] px-3 py-2 text-[12px] text-[var(--muted2)]">
                Отмена
              </button>
              <button type="button" onClick={submit} className="rounded-lg bg-[var(--accent)] px-3 py-2 text-[12px] font-semibold text-black disabled:opacity-50" disabled={!title.trim()}>
                Сохранить
              </button>
            </div>
          </motion.div>
        </>
      ) : null}
    </AnimatePresence>
  )
}
