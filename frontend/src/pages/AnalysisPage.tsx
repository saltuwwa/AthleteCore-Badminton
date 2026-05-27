import { motion } from 'framer-motion'
import { Link } from 'react-router-dom'
import { PageTabs } from '../components/layout/PageTabs'

const item = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] as const } },
}

export const AnalysisPage = () => {
  return (
    <motion.div
      initial="hidden"
      animate="visible"
      variants={{ visible: { transition: { staggerChildren: 0.06 } } }}
      className="thin-scrollbar flex h-full flex-col overflow-y-auto"
    >
      <div className="flex items-start justify-between gap-4 px-8 pb-4 pt-7">
        <motion.div variants={item}>
          <p className="label-mono">AthleteCore · Analysis</p>
          <h1 className="font-display mt-2 text-[34px] leading-[0.95] tracking-tight">Анализ</h1>
          <p className="mt-2 max-w-md text-[12.5px] text-[var(--muted2)]">
            Разбор матча по видео или текстовый лог в чате.
          </p>
        </motion.div>
        <motion.div variants={item}>
          <PageTabs />
        </motion.div>
      </div>

      <motion.section variants={item} className="mx-8 max-w-lg">
        <Link
          to="/analysis/video"
          className="group block rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-8 backdrop-blur-sm transition hover:border-[var(--accent)]"
          style={{ boxShadow: 'var(--glow-purple)' }}
        >
          <p className="font-display text-[22px] tracking-tight group-hover:text-[var(--accent-strong)]">
            Разбор видео матча
          </p>
          <p className="mt-2 text-[13px] text-[var(--muted2)]">
            Загрузи запись — получи скорость, усталость, паттерны и сравнение с прошлыми играми.
          </p>
          <span className="mt-6 inline-flex rounded-lg bg-[var(--accent)] px-4 py-2 text-[13px] font-semibold text-white">
            Начать →
          </span>
        </Link>

        <Link
          to="/chat"
          className="mt-4 block rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] px-6 py-4 text-[13px] text-[var(--muted2)] transition hover:border-[var(--border-strong)]"
        >
          Или опиши матч в <span className="text-[var(--accent)]">чате</span>
        </Link>
      </motion.section>
    </motion.div>
  )
}
