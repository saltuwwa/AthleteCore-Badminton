import { motion } from 'framer-motion'
import { Link } from 'react-router-dom'
import { ChatEntryBar } from '../components/chat/ChatEntryBar'
import { PageTabs } from '../components/layout/PageTabs'
import { SignalStrip } from '../components/layout/SignalStrip'

const container = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.05 } },
}
const item = {
  hidden: { opacity: 0, y: 10 },
  visible: { opacity: 1, y: 0, transition: { duration: 0.35, ease: [0.22, 1, 0.36, 1] as const } },
}

export const Overview = () => {
  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="visible"
      className="flex h-full flex-col overflow-hidden"
    >
      <div className="thin-scrollbar min-h-0 flex-1 overflow-y-auto">
        <div className="flex items-start justify-between gap-4 px-8 pb-4 pt-7">
          <motion.div variants={item}>
            <p className="label-mono">Welcome back · AthleteCore</p>
            <h1 className="font-display mt-2 text-[34px] leading-[0.95] tracking-tight">
              Добро пожаловать, <span className="text-[var(--accent)]">Айгерим</span>
            </h1>
            <p className="mt-2 max-w-lg text-[12.5px] text-[var(--muted2)]">
              Сегодня фокус на стабильной нагрузке и качестве движений. AI-ассистент — внизу или во вкладке «Чат».
            </p>
          </motion.div>
          <motion.div variants={item}>
            <PageTabs />
          </motion.div>
        </div>

        <div className="diagonal-divider mx-8 h-px" />
        <SignalStrip
          title="Daily Focus"
          items={[
            { label: 'STATE', value: 'READY', tone: 'good' },
            { label: 'TODAY LOAD', value: 'MODERATE', tone: 'accent' },
            { label: 'RECOVERY', value: '76%', tone: 'good' },
            { label: 'NEXT EVENT', value: '18:00 TRAINING', tone: 'neutral' },
            { label: 'BWF', value: '#543', tone: 'accent' },
          ]}
        />

        <motion.section variants={item} className="grid grid-cols-3 gap-3 px-8 pt-6">
          <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
            <p className="label-mono">План на сегодня</p>
            <p className="font-display mt-2 text-[20px] tracking-tight">Техника + восстановление</p>
            <p className="mt-2 text-[12px] text-[var(--muted2)]">2 ключевых блока, без перегруза.</p>
          </article>
          <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
            <p className="label-mono">Ментальная готовность</p>
            <p className="font-display mt-2 text-[20px] tracking-tight">Высокая</p>
            <p className="mt-2 text-[12px] text-[var(--muted2)]">Рекомендуется короткая предматчевая визуализация.</p>
          </article>
          <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
            <p className="label-mono">Риск перегруза</p>
            <p className="font-display mt-2 text-[20px] tracking-tight text-[var(--accent2)]">Низкий</p>
            <p className="mt-2 text-[12px] text-[var(--muted2)]">Сон и пульс в норме, можно держать план.</p>
          </article>
        </motion.section>

        <motion.section variants={item} className="grid grid-cols-[1.25fr_1fr] gap-3 px-8 pb-6 pt-5">
          <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
            <p className="font-display text-[16px] tracking-tight">Что сделать сейчас</p>
            <ul className="mt-3 space-y-2 text-[12.5px] text-[var(--text-soft)]">
              <li className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2">
                1) Проверить расписание и подтвердить блоки на сегодня
              </li>
              <li className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2">
                2) После сессии — голосовой лог в чате
              </li>
              <li className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2">
                3) Открыть «Анализ» для разбора розыгрышей
              </li>
            </ul>
          </article>
          <article className="rounded-2xl border border-[var(--border)] bg-[var(--surface-glass)] p-5 backdrop-blur-sm">
            <p className="font-display text-[16px] tracking-tight">Быстрые действия</p>
            <div className="mt-3 grid gap-2">
              <Link
                to="/schedule"
                className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-[12px] hover:border-[var(--accent)]"
              >
                Открыть расписание
              </Link>
              <Link
                to="/analysis"
                className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-[12px] hover:border-[var(--accent)]"
              >
                Анализ матча
              </Link>
              <Link
                to="/health"
                className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-2 text-[12px] hover:border-[var(--accent)]"
              >
                Проверить здоровье
              </Link>
            </div>
          </article>
        </motion.section>
      </div>

      <motion.div variants={item}>
        <ChatEntryBar />
      </motion.div>
    </motion.div>
  )
}
