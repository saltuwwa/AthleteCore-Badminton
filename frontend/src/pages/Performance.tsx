import { motion } from 'framer-motion'
import { Bars } from '../components/charts/Bars'
import { Sparkline } from '../components/charts/Sparkline'
import { PageTabs } from '../components/layout/PageTabs'
import { SignalStrip } from '../components/layout/SignalStrip'
import {
  bwfRankHistory,
  matchScores,
  monthlyTrainingLoad,
  recentMatches,
  winRateHistory,
} from '../data/progressData'

const lastDelta = (arr: number[]) => arr[arr.length - 1] - arr[arr.length - 2]

const container = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
}
const item = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] as const } },
}

export const Performance = () => {
  const score = matchScores[matchScores.length - 1]
  const scoreDelta = lastDelta(matchScores).toFixed(1)
  const rank = bwfRankHistory[bwfRankHistory.length - 1]
  const rankDelta = bwfRankHistory[bwfRankHistory.length - 2] - rank
  const winRate = winRateHistory[winRateHistory.length - 1]
  const winDelta = lastDelta(winRateHistory)

  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="visible"
      className="thin-scrollbar flex h-full flex-col overflow-y-auto"
    >
      <div className="flex items-start justify-between gap-4 px-8 pb-4 pt-7">
        <motion.div variants={item}>
          <p className="label-mono">Career trajectory · YTD</p>
          <h1 className="font-display mt-2 text-[34px] leading-[0.95] tracking-tight">
            Прогресс <span className="text-[var(--accent2)]">/ 12 мес</span>
          </h1>
          <p className="mt-2 max-w-lg text-[12.5px] text-[var(--muted2)]">
            Ключевые KPI карьеры: оценка матча, ранг BWF, win rate. Все цифры синхронизированы с user_history индексом.
          </p>
        </motion.div>
        <motion.div variants={item}>
          <PageTabs />
        </motion.div>
      </div>

      <div className="diagonal-divider mx-8 h-px" />
      <SignalStrip
        title="Season Momentum"
        items={[
          { label: 'MATCH SCORE', value: `${score.toFixed(1)} avg`, tone: 'good' },
          { label: 'WIN RATE', value: `${winRate}%`, tone: 'good' },
          { label: 'RANK DELTA', value: `+${rankDelta}`, tone: 'accent' },
          { label: 'UNFORCED ERR', value: '-12%', tone: 'good' },
          { label: 'CURRENT FORM', value: 'UPTREND', tone: 'accent' },
        ]}
      />

      <motion.section variants={item} className="grid grid-cols-3 gap-3 px-8 pt-6">
        <article className="crosshair-corner relative rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
          <p className="label-mono">Match score</p>
          <p className="hero-number mt-3 text-[56px]">{score.toFixed(1)}</p>
          <p className="label-mono mt-1 text-[var(--accent2)]">+{scoreDelta} к прошлому месяцу</p>
          <div className="mt-3 h-14"><Sparkline values={matchScores} /></div>
        </article>
        <article className="crosshair-corner relative rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
          <p className="label-mono">BWF rank</p>
          <p className="hero-number mt-3 text-[56px]">
            <span className="text-[var(--muted)]">#</span>{rank}
          </p>
          <p className="label-mono mt-1 text-[var(--accent2)]">+{rankDelta} позиций</p>
          <div className="mt-3 h-14">
            <Sparkline values={bwfRankHistory.map((v) => -v)} color="var(--accent2)" fill="rgba(184,255,107,0.18)" />
          </div>
        </article>
        <article className="crosshair-corner relative rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
          <p className="label-mono">Win rate</p>
          <p className="hero-number mt-3 text-[56px]">{winRate}<span className="text-[28px] text-[var(--muted2)]">%</span></p>
          <p className="label-mono mt-1 text-[var(--accent2)]">+{winDelta} % YTD</p>
          <div className="mt-3 h-14"><Sparkline values={winRateHistory} color="var(--amber)" fill="rgba(255,200,60,0.18)" /></div>
        </article>
      </motion.section>

      <motion.section variants={item} className="grid grid-cols-[1.5fr_1fr] gap-3 px-8 pt-5">
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
          <div className="flex items-center justify-between">
            <p className="font-display text-[15px] tracking-tight">Тренировочная нагрузка</p>
            <span className="label-mono">часы / месяц</span>
          </div>
          <div className="mt-4"><Bars values={monthlyTrainingLoad} /></div>
        </article>
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
          <p className="font-display text-[15px] tracking-tight">Тренды 30 дней</p>
          <ul className="mt-3 space-y-2">
            {[
              { label: 'Скорость реакции', delta: '+8 %', tone: 'good' },
              { label: 'Точность смешей', delta: '+5 %', tone: 'good' },
              { label: 'Невынужденные ошибки', delta: '-12 %', tone: 'good' },
              { label: 'Длительность розыгрышей', delta: '+0.4 с', tone: 'neutral' },
            ].map((t) => (
              <li key={t.label} className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2">
                <span className="text-[12px] text-[var(--text-soft)]">{t.label}</span>
                <span className={`font-mono-ui text-[11px] ${t.tone === 'good' ? 'text-[var(--accent2)]' : 'text-[var(--muted2)]'}`}>{t.delta}</span>
              </li>
            ))}
          </ul>
        </article>
      </motion.section>

      <motion.section variants={item} className="px-8 pb-8 pt-5">
        <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
          <div className="mb-3 flex items-center justify-between">
            <p className="font-display text-[15px] tracking-tight">Последние матчи</p>
            <span className="label-mono">оценка · ошибки · результат</span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[12px]">
              <thead>
                <tr className="text-left">
                  {['Дата', 'Соперник', 'Турнир', 'Результат', 'Оценка', 'Ошибки'].map((h) => (
                    <th key={h} className="label-mono pb-2">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {recentMatches.map((m) => (
                  <tr key={m.id} className="border-t border-[var(--border)]">
                    <td className="py-3 text-[var(--muted2)]">{m.date}</td>
                    <td className="py-3 font-display">{m.opponent}</td>
                    <td className="py-3 text-[var(--muted2)]">{m.tournament}</td>
                    <td className="py-3">
                      <span className={m.result.startsWith('W') ? 'text-[var(--accent2)]' : 'text-[var(--accent3)]'}>{m.result}</span>
                    </td>
                    <td className="py-3 text-right">
                      <span className="font-display tabular-nums text-[15px]">{m.score.toFixed(1)}</span>
                    </td>
                    <td className="py-3 text-right font-mono-ui text-[var(--accent3)]">{m.errors}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      </motion.section>
    </motion.div>
  )
}
