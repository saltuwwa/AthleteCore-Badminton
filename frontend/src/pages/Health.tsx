import { motion } from 'framer-motion'
import { Bars } from '../components/charts/Bars'
import { Sparkline } from '../components/charts/Sparkline'
import { PageTabs } from '../components/layout/PageTabs'
import { SignalStrip } from '../components/layout/SignalStrip'
import {
  nutritionTargets,
  recoveryScore,
  restingHr,
  rpe,
  sleepHours,
  weekDays,
  wellnessNotes,
} from '../data/healthData'

const last = (arr: number[]) => arr[arr.length - 1]

const container = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
}
const item = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] as const } },
}

const kpiCards = [
  {
    label: 'Сон сегодня',
    value: `${last(sleepHours).toFixed(1)} ч`,
    spark: sleepHours,
    color: 'var(--cyan)',
    fill: 'rgba(95,188,255,0.18)',
  },
  {
    label: 'Пульс покоя',
    value: `${last(restingHr)} bpm`,
    spark: restingHr.map((v) => -v),
    color: 'var(--accent2)',
    fill: 'rgba(184,255,107,0.18)',
  },
  {
    label: 'RPE последняя',
    value: `${last(rpe)}/10`,
    spark: rpe,
    color: 'var(--amber)',
    fill: 'rgba(255,200,60,0.18)',
  },
  {
    label: 'Recovery score',
    value: `${last(recoveryScore)}%`,
    spark: recoveryScore,
    color: 'var(--accent)',
    fill: 'rgba(124,107,255,0.2)',
  },
]

export const Health = () => {
  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="visible"
      className="thin-scrollbar flex h-full flex-col overflow-y-auto"
    >
      <div className="flex items-start justify-between gap-4 px-8 pb-4 pt-7">
        <motion.div variants={item}>
          <p className="label-mono">Recovery cockpit · today</p>
          <h1 className="font-display mt-2 text-[34px] leading-[0.95] tracking-tight">
            Здоровье <span className="text-[var(--cyan)]">/ live</span>
          </h1>
          <p className="mt-2 max-w-lg text-[12.5px] text-[var(--muted2)]">
            Health Coach агент сводит сон, нагрузку, питание и физиологию в один recovery score. Цвета следуют той же
            семантике, что и в Analyst.
          </p>
        </motion.div>
        <motion.div variants={item}>
          <PageTabs />
        </motion.div>
      </div>

      <div className="diagonal-divider mx-8 h-px" />
      <SignalStrip
        title="Recovery Signals"
        items={[
          { label: 'SLEEP', value: `${last(sleepHours).toFixed(1)}h`, tone: 'good' },
          { label: 'REST HR', value: `${last(restingHr)} bpm`, tone: 'neutral' },
          { label: 'RPE', value: `${last(rpe)}/10`, tone: 'alert' },
          { label: 'HYDRATION', value: '2.4 / 3.2L', tone: 'accent' },
          { label: 'RECOVERY SCORE', value: `${last(recoveryScore)}%`, tone: 'good' },
        ]}
      />

      <motion.section variants={item} className="grid grid-cols-4 gap-3 px-8 pt-6">
        {kpiCards.map((k) => (
          <article key={k.label} className="crosshair-corner relative rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
            <p className="label-mono">{k.label}</p>
            <p className="hero-number mt-3 text-[40px]" style={{ color: k.color }}>{k.value}</p>
            <div className="mt-2 h-12"><Sparkline values={k.spark} color={k.color} fill={k.fill} /></div>
          </article>
        ))}
      </motion.section>

      <motion.section variants={item} className="grid grid-cols-[1.4fr_1fr] gap-3 px-8 pt-5">
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
          <p className="font-display text-[15px] tracking-tight">Нагрузка по дням (RPE)</p>
          <p className="label-mono mt-1">Шкала Borg · 0-10</p>
          <div className="mt-4">
            <Bars
              values={rpe.map((v, i) => ({
                label: weekDays[i],
                value: v,
                color: v >= 7 ? 'rgba(255,107,138,0.65)' : v >= 5 ? 'rgba(124,107,255,0.6)' : 'rgba(184,255,107,0.6)',
              }))}
              max={10}
            />
          </div>
        </article>
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
          <p className="font-display text-[15px] tracking-tight">Питание сегодня</p>
          <div className="mt-4 space-y-3">
            {nutritionTargets.map((n) => {
              const pct = Math.min(100, Math.round((n.value / n.target) * 100))
              return (
                <div key={n.label}>
                  <div className="flex items-baseline justify-between text-[12px]">
                    <span className="font-display">{n.label}</span>
                    <span className="font-mono-ui text-[11px] text-[var(--muted2)]">{n.value} / {n.target} {n.unit}</span>
                  </div>
                  <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-[var(--bg3)]">
                    <div
                      className="h-full"
                      style={{ width: `${pct}%`, background: pct >= 85 ? 'var(--accent2)' : 'var(--accent)' }}
                    />
                  </div>
                </div>
              )
            })}
          </div>
        </article>
      </motion.section>

      <motion.section variants={item} className="px-8 pb-8 pt-5">
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
          <p className="font-display text-[15px] tracking-tight">Заметки Health Coach</p>
          <ul className="mt-3 grid grid-cols-3 gap-3">
            {wellnessNotes.map((n) => (
              <li key={n.id} className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-4">
                <p className="label-mono">{n.date}</p>
                <p className="mt-2 text-[12.5px] leading-relaxed text-[var(--text-soft)]">{n.text}</p>
              </li>
            ))}
          </ul>
        </article>
      </motion.section>
    </motion.div>
  )
}
