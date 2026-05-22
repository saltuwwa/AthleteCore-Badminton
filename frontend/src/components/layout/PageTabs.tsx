import { motion } from 'framer-motion'
import { NavLink } from 'react-router-dom'

const tabs = [
  { to: '/overview', label: 'Обзор' },
  { to: '/chat', label: 'Чат' },
  { to: '/analysis', label: 'Анализ' },
  { to: '/schedule', label: 'Расписание' },
  { to: '/progress', label: 'Прогресс' },
  { to: '/health', label: 'Здоровье' },
  { to: '/history', label: 'История' },
]

export const PageTabs = () => {
  return (
    <div className="relative flex items-center gap-1 rounded-full border border-[var(--border)] bg-[var(--surface-1)] p-1 backdrop-blur-md">
      {tabs.map((tab) => (
        <NavLink key={tab.to} to={tab.to} className="relative">
          {({ isActive }) => (
            <span
              className={`relative z-10 inline-block rounded-full px-4 py-1.5 font-display text-[12px] transition-colors ${
                isActive ? 'text-[var(--bg-deep)]' : 'text-[var(--muted2)] hover:text-[var(--text-primary)]'
              }`}
            >
              {isActive ? (
                <motion.span
                  layoutId="tab-active-bg"
                  className="absolute inset-0 -z-10 rounded-full bg-[var(--accent2)]"
                  transition={{ type: 'spring', damping: 26, stiffness: 320 }}
                />
              ) : null}
              {tab.label}
            </span>
          )}
        </NavLink>
      ))}
    </div>
  )
}
