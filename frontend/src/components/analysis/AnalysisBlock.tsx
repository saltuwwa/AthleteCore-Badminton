import { motion } from 'framer-motion'
import type { AnalysisErrorRow } from '../../lib/chatMappers'

const defaultErrors: AnalysisErrorRow[] = [
  {
    level: 'HIGH',
    title: 'Защита по корту слева после длинных розыгрышей',
    cause: 'Поздний выход из задней линии · 3-й матч подряд',
    fix: 'Добавить блок реакции на укороченные слева, 12 мин × 2',
    pattern: '3-я итерация за 2 недели',
  },
  {
    level: 'MED',
    title: 'Подача в розыгрышах >12 ударов',
    cause: 'Падение точности с 78 % до 61 %',
    fix: 'Перевод темпа на 7-м ударе, серии 5 × 8',
    pattern: '',
  },
  {
    level: 'LOW',
    title: 'Постановка ног при ремайзе сетки',
    cause: 'Изолированный случай в 2-м сете',
    fix: 'Мобилити стопы перед матчем',
    pattern: '',
  },
]

const levelStyles = {
  HIGH: { color: 'var(--accent3)', bg: 'rgba(255,107,138,0.13)', border: 'rgba(255,107,138,0.4)', label: 'CRITICAL' },
  MED: { color: 'var(--amber)', bg: 'rgba(255,200,60,0.12)', border: 'rgba(255,200,60,0.35)', label: 'WATCH' },
  LOW: { color: 'var(--accent2)', bg: 'rgba(184,255,107,0.1)', border: 'rgba(184,255,107,0.3)', label: 'NOTE' },
} as const

type Props = {
  errors?: AnalysisErrorRow[]
  live?: boolean
}

export const AnalysisBlock = ({ errors, live = false }: Props) => {
  const rows = errors?.length ? errors : defaultErrors

  return (
    <section className="crosshair-corner relative rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
      <div className="flex items-start justify-between gap-4">
        <div>
          <p className="label-mono">Analyst Agent · {live ? 'Live' : 'Demo'}</p>
          <h2 className="font-display mt-2 text-[22px] leading-tight tracking-tight">
            Корневой анализ ошибок{' '}
            <span className="text-[var(--accent)]">/{String(rows.length).padStart(2, '0')}</span>
          </h2>
          <p className="mt-2 max-w-xl text-[12.5px] text-[var(--muted2)]">
            {live
              ? 'Данные из последнего ответа Analyst (JSON из LangGraph).'
              : 'Пример до первого запроса в чат — отправь разбор матча ниже.'}
          </p>
        </div>
        <div className="flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--bg2)] px-3 py-1.5">
          <span className="relative h-2 w-2">
            <span className="absolute inset-0 rounded-full bg-[var(--accent)]" />
            <span className="pulse-ring" style={{ color: 'var(--accent)' }} />
          </span>
          <span className="label-mono">{live ? 'From API' : 'Pattern engine'}</span>
        </div>
      </div>

      <div className="mt-5 space-y-2.5">
        {rows.map((e, i) => {
          const s = levelStyles[e.level]
          return (
            <motion.article
              key={`${e.title}-${i}`}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.08 * i, duration: 0.25 }}
              className="grid grid-cols-[88px_1fr_1fr] items-start gap-4 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3"
            >
              <div
                className="rounded-md border px-2 py-1 text-center"
                style={{ background: s.bg, borderColor: s.border, color: s.color }}
              >
                <p className="font-mono-ui text-[9px] tracking-[0.18em]">{s.label}</p>
                <p className="font-display mt-0.5 text-[14px] font-semibold">{e.level}</p>
              </div>
              <div>
                <p className="font-display text-[13px] text-[var(--text-primary)]">{e.title}</p>
                <p className="mt-1 text-[11.5px] text-[var(--muted2)]">{e.cause}</p>
                {e.pattern ? (
                  <p className="label-mono mt-2 text-[var(--accent)]">↻ {e.pattern}</p>
                ) : null}
              </div>
              <div className="rounded-lg border border-dashed border-[var(--border)] bg-[var(--bg-deep)] p-2">
                <p className="label-mono text-[var(--muted)]">Корректирующее действие</p>
                <p className="mt-1 text-[12px] text-[var(--text-soft)]">{e.fix}</p>
              </div>
            </motion.article>
          )
        })}
      </div>
    </section>
  )
}
