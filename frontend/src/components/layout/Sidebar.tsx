import { motion } from 'framer-motion'
import { NavLink } from 'react-router-dom'

type NavItem = { to: string; label: string; index: string }

const navItems: NavItem[] = [
  { to: '/home', label: 'Главная', index: '01' },
  { to: '/chat', label: 'Чат', index: '02' },
  { to: '/analysis', label: 'Анализ', index: '03' },
  { to: '/schedule', label: 'Расписание', index: '04' },
  { to: '/progress', label: 'Прогресс', index: '05' },
  { to: '/health', label: 'Здоровье', index: '06' },
  { to: '/history', label: 'История', index: '07' },
]

const agents = [
  { name: 'Planner', status: 'active' as const },
  { name: 'Analyst', status: 'processing' as const },
  { name: 'Health Coach', status: 'idle' as const },
]

const statusColor = (s: 'active' | 'processing' | 'idle') =>
  s === 'active' ? 'var(--accent2)' : s === 'processing' ? 'var(--accent)' : 'var(--muted)'

export const Sidebar = ({
  onOpenProfile,
  theme,
  onToggleTheme,
}: {
  onOpenProfile: () => void
  theme: 'dark' | 'light'
  onToggleTheme: () => void
}) => {
  return (
    <aside className="relative flex h-screen flex-col border-r border-[var(--border)] bg-[var(--surface-1)] backdrop-blur-xl">
      <div className="relative px-5 pt-5 pb-4">
        <div className="flex items-center justify-between">
          <div className="flex items-baseline gap-2">
            <span className="font-display text-[19px] font-semibold tracking-tight">Athlete</span>
            <span className="font-display text-[19px] font-semibold tracking-tight text-[var(--accent)]">Core</span>
          </div>
          <button type="button" onClick={onToggleTheme} className="theme-toggle">
            {theme === 'dark' ? 'Light' : 'Dark'}
          </button>
        </div>
        <p className="label-mono mt-2">SYS · v0.1 · LIVE</p>
        <span className="absolute right-4 top-6 h-2 w-2 rounded-full bg-[var(--accent2)] shadow-[0_0_12px_rgba(184,255,107,0.7)]" />
      </div>

      <div className="diagonal-divider mx-5 h-px" />

      <nav className="mt-5 flex flex-col gap-0.5 px-2">
        <p className="label-mono mb-2 px-3">Workspace</p>
        {navItems.map((item) => (
          <NavLink key={item.to} to={item.to} className="group block">
            {({ isActive }) => (
              <div
                className={`relative flex items-center gap-3 rounded-lg px-3 py-2 transition-colors ${
                  isActive
                    ? 'bg-[var(--surface-2)] text-[var(--text-primary)]'
                    : 'text-[var(--muted2)] hover:bg-[var(--bg3)] hover:text-[var(--text-primary)]'
                }`}
              >
                {isActive ? (
                  <motion.span
                    layoutId="nav-active-bar"
                    className="absolute inset-y-2 left-0 w-[3px] rounded-full bg-[var(--accent)]"
                    transition={{ type: 'spring', damping: 26, stiffness: 320 }}
                  />
                ) : null}
                <span className={`font-mono-ui text-[10px] ${isActive ? 'text-[var(--accent)]' : 'text-[var(--muted)]'}`}>
                  {item.index}
                </span>
                <span className="font-display text-[13px]">{item.label}</span>
              </div>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="mt-6 px-5">
        <p className="label-mono mb-2">Agents</p>
        <div className="space-y-1.5">
          {agents.map((a) => (
            <div
              key={a.name}
              className="flex items-center justify-between rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-3 py-1.5"
            >
              <span className="font-display text-[11px] text-[var(--text-soft)]">{a.name}</span>
              <div className="relative h-2 w-2">
                <span
                  className="absolute inset-0 rounded-full"
                  style={{ background: statusColor(a.status) }}
                />
                {a.status === 'processing' ? (
                  <span className="pulse-ring" style={{ color: statusColor(a.status) }} />
                ) : null}
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-auto px-3 pb-3">
        <button
          type="button"
          onClick={onOpenProfile}
          className="crosshair-corner relative flex w-full items-center gap-3 rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3 text-left transition-colors hover:border-[var(--accent)] hover:bg-[var(--bg3)]"
        >
          <div className="relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[var(--accent)] to-[#5a4bff] font-display text-[12px] font-semibold text-white">
            АС
            <span className="absolute -bottom-0.5 -right-0.5 h-2.5 w-2.5 rounded-full border-2 border-[var(--bg2)] bg-[var(--accent2)]" />
          </div>
          <div className="min-w-0 flex-1">
            <p className="truncate font-display text-[12px] text-[var(--text-primary)]">Айгерим Смагулова</p>
            <p className="label-mono mt-0.5">BWF #543 · WS</p>
          </div>
          <span className="font-mono-ui text-[10px] text-[var(--muted)]">↗</span>
        </button>
      </div>
    </aside>
  )
}
