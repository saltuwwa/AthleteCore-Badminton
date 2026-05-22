import { motion } from 'framer-motion'
import { AnalysisBlock } from '../components/analysis/AnalysisBlock'
import { Sparkline } from '../components/charts/Sparkline'
import { PageTabs } from '../components/layout/PageTabs'
import { SignalStrip } from '../components/layout/SignalStrip'
import { matchScores } from '../data/progressData'

const container = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.08 } },
}
const item = {
  hidden: { opacity: 0, y: 12 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.4, ease: [0.22, 1, 0.36, 1] as const } },
}

export const AnalysisPage = () => {
  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="visible"
      className="thin-scrollbar flex h-full flex-col overflow-y-auto"
    >
      <div className="flex items-start justify-between gap-4 px-8 pb-4 pt-7">
        <motion.div variants={item}>
          <p className="label-mono">SESSION · 21 APR · 19:40 GMT+5</p>
          <h1 className="font-display mt-2 text-[34px] leading-[0.95] tracking-tight">
            Матч против <span className="text-[var(--accent)]">А. Жакаевой</span>
          </h1>
          <p className="mt-2 max-w-lg text-[12.5px] text-[var(--muted2)]">
            Almaty Cup · WS · 2-1. Разбор ошибок и паттернов по матчу — без чата (AI на вкладке «Чат»).
          </p>
        </motion.div>
        <motion.div variants={item}>
          <PageTabs />
        </motion.div>
      </div>

      <div className="diagonal-divider mx-8 h-px" />
      <SignalStrip
        title="Live Performance Feed"
        items={[
          { label: 'REACTION', value: '+8%', tone: 'good' },
          { label: 'RALLY AVG', value: '11.4 hits', tone: 'accent' },
          { label: 'ERROR CLUSTER', value: 'LEFT DEFENCE', tone: 'alert' },
          { label: 'RECOVERY', value: '76%', tone: 'good' },
          { label: 'BWF TREND', value: '#543 → #539', tone: 'neutral' },
        ]}
      />

      <motion.section variants={item} className="px-8 pt-6">
        <div className="crosshair-corner relative grid grid-cols-[1.4fr_1fr_1fr_1fr] gap-6 rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-6 backdrop-blur-sm">
          <div className="border-r border-[var(--border)] pr-6">
            <p className="label-mono">Match score</p>
            <div className="mt-2 flex items-baseline gap-3">
              <span className="hero-number text-[88px] text-[var(--text-primary)]">8.6</span>
              <span className="font-mono-ui text-[12px] text-[var(--accent2)]">+0.4 ↑</span>
            </div>
            <div className="mt-3 h-12">
              <Sparkline values={matchScores} />
            </div>
            <p className="label-mono mt-3">За 12 матчей · сезон 25/26</p>
          </div>

          <div>
            <p className="label-mono">Ошибки</p>
            <p className="hero-number mt-2 text-[64px] text-[var(--accent3)]">07</p>
            <p className="label-mono mt-2">из них критических · 02</p>
          </div>

          <div>
            <p className="label-mono">Нагрузка недели</p>
            <p className="hero-number mt-2 text-[64px] text-[var(--accent2)]">74%</p>
            <p className="label-mono mt-2">Recovery debt · -12 %</p>
          </div>

          <div>
            <p className="label-mono">Pattern density</p>
            <p className="hero-number mt-2 text-[64px] text-[var(--accent)]">3.2×</p>
            <p className="label-mono mt-2">vs прошлый месяц</p>
          </div>
        </div>
      </motion.section>

      <motion.section variants={item} className="px-8 pb-8 pt-5">
        <AnalysisBlock />
      </motion.section>
    </motion.div>
  )
}
