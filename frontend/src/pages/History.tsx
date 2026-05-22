import { motion } from 'framer-motion'
import { useMemo, useState } from 'react'
import { PageTabs } from '../components/layout/PageTabs'
import { SignalStrip } from '../components/layout/SignalStrip'
import type { HistoryItemType } from '../data/historyData'
import { historyItems } from '../data/historyData'

const filters: { value: HistoryItemType | 'ALL'; label: string }[] = [
  { value: 'ALL', label: 'Все' },
  { value: 'MATCH', label: 'Матчи' },
  { value: 'TRAINING', label: 'Тренировки' },
  { value: 'VOICE', label: 'Голос' },
  { value: 'NOTE', label: 'Заметки' },
]

const typeStyles: Record<HistoryItemType, { color: string; bg: string; label: string }> = {
  MATCH: { color: 'var(--accent3)', bg: 'rgba(255,107,138,0.18)', label: 'Матч' },
  TRAINING: { color: 'var(--accent)', bg: 'rgba(124,107,255,0.18)', label: 'Тренировка' },
  VOICE: { color: 'var(--cyan)', bg: 'rgba(95,188,255,0.18)', label: 'Голос' },
  NOTE: { color: 'var(--amber)', bg: 'rgba(255,200,60,0.18)', label: 'Заметка' },
}

const container = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.05, delayChildren: 0.05 } },
}
const item = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.32, ease: [0.22, 1, 0.36, 1] as const } },
}

export const History = () => {
  const [filter, setFilter] = useState<HistoryItemType | 'ALL'>('ALL')
  const [search, setSearch] = useState('')

  const items = useMemo(() => {
    return historyItems.filter((entry) => {
      const okType = filter === 'ALL' || entry.type === filter
      const okSearch =
        !search.trim() ||
        entry.title.toLowerCase().includes(search.toLowerCase()) ||
        entry.summary.toLowerCase().includes(search.toLowerCase())
      return okType && okSearch
    })
  }, [filter, search])

  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="visible"
      className="thin-scrollbar flex h-full flex-col overflow-y-auto"
    >
      <div className="flex items-start justify-between gap-4 px-8 pb-4 pt-7">
        <motion.div variants={item}>
          <p className="label-mono">Athletic logbook · RAG-indexed</p>
          <h1 className="font-display mt-2 text-[34px] leading-[0.95] tracking-tight">
            История <span className="text-[var(--accent3)]">/ паттерны</span>
          </h1>
          <p className="mt-2 max-w-lg text-[12.5px] text-[var(--muted2)]">
            Все логи — матчи, тренировки, голосовые заметки — попадают в user_history. Аналитик подсвечивает повторы.
          </p>
        </motion.div>
        <motion.div variants={item}>
          <PageTabs />
        </motion.div>
      </div>

      <div className="diagonal-divider mx-8 h-px" />
      <SignalStrip
        title="History Intelligence"
        items={[
          { label: 'TOTAL LOGS', value: `${historyItems.length}`, tone: 'neutral' },
          { label: 'RECURRING PATTERNS', value: '3 active', tone: 'alert' },
          { label: 'VOICE LOGS', value: '12 entries', tone: 'accent' },
          { label: 'LATEST MATCH', value: 'W 2-1', tone: 'good' },
          { label: 'INDEX STATUS', value: 'Qdrant synced', tone: 'good' },
        ]}
      />

      <motion.header variants={item} className="flex flex-wrap items-center justify-between gap-3 px-8 pt-6">
        <div className="flex flex-wrap gap-1 rounded-full border border-[var(--border)] bg-[var(--surface-1)] p-1 backdrop-blur-md">
          {filters.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setFilter(f.value)}
              className={`rounded-full px-4 py-1.5 font-display text-[12px] transition-colors ${
                filter === f.value ? 'bg-[var(--accent)] text-white' : 'text-[var(--muted2)] hover:text-[var(--text-primary)]'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по записям..."
          className="w-72 rounded-full border border-[var(--border)] bg-[var(--surface-1)] px-4 py-2 text-[12px] outline-none backdrop-blur-md focus:border-[var(--accent)]"
        />
      </motion.header>

      <motion.section variants={item} className="px-8 pb-8 pt-5">
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
          {items.length === 0 ? (
            <p className="p-4 text-[12px] text-[var(--muted2)]">Ничего не найдено по текущему фильтру.</p>
          ) : (
            <ul className="relative space-y-3 pl-6 before:absolute before:left-2 before:top-3 before:bottom-3 before:w-px before:bg-[var(--border-strong)]">
              {items.map((entry) => {
                const meta = typeStyles[entry.type]
                return (
                  <li key={entry.id} className="relative rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-4">
                    <span
                      className="absolute -left-[22px] top-4 h-3.5 w-3.5 rounded-full border-2 border-[var(--bg2)]"
                      style={{ background: meta.color }}
                    />
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="label-mono">{entry.date}</p>
                        <p className="font-display mt-1 text-[14px] tracking-tight">{entry.title}</p>
                        <p className="mt-2 max-w-2xl text-[12.5px] leading-relaxed text-[var(--muted2)]">{entry.summary}</p>
                      </div>
                      <span
                        className="shrink-0 rounded-full px-3 py-1 font-mono-ui text-[10px] tracking-wider"
                        style={{ background: meta.bg, color: meta.color }}
                      >
                        {meta.label}
                      </span>
                    </div>
                    {entry.tags ? (
                      <div className="mt-3 flex flex-wrap gap-1.5">
                        {entry.tags.map((tag) => (
                          <span key={tag} className="rounded-full border border-[var(--border)] px-2.5 py-1 font-mono-ui text-[10px] tracking-wider text-[var(--muted2)]">
                            {tag}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </li>
                )
              })}
            </ul>
          )}
        </article>
      </motion.section>
    </motion.div>
  )
}
