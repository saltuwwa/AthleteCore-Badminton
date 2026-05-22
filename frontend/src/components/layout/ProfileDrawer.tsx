import { AnimatePresence, motion } from 'framer-motion'
import { useEffect } from 'react'
import { BWFRankCard } from '../profile/BWFRankCard'

type Props = {
  isOpen: boolean
  onClose: () => void
}

const connections = [
  { initials: 'МК', name: 'Марат Кайратов', rank: 614, online: true },
  { initials: 'ДТ', name: 'Дина Турсунова', rank: 482, online: false },
  { initials: 'РН', name: 'Руслан Нургалиев', rank: 533, online: true },
]

const stats = [
  { label: 'Win rate', value: '68%', tone: 'var(--text-primary)' },
  { label: 'BWF очки', value: '12 420', tone: 'var(--text-primary)' },
  { label: 'Турниров', value: '17', tone: 'var(--text-primary)' },
  { label: 'Ранг YTD', value: '+43', tone: 'var(--accent2)' },
]

export const ProfileDrawer = ({ isOpen, onClose }: Props) => {
  useEffect(() => {
    if (!isOpen) return
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [isOpen, onClose])

  return (
    <AnimatePresence>
      {isOpen ? (
        <>
          <motion.button
            type="button"
            onClick={onClose}
            className="fixed inset-0 z-40 bg-black/65 backdrop-blur-sm"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
          />
          <motion.aside
            className="fixed right-0 top-0 z-50 flex h-screen w-full max-w-[440px] flex-col gap-4 border-l border-[var(--border-strong)] bg-[var(--surface-1)] p-5 backdrop-blur-xl"
            initial={{ x: 480 }}
            animate={{ x: 0 }}
            exit={{ x: 480 }}
            transition={{ type: 'spring', damping: 28, stiffness: 280 }}
          >
            <div className="flex items-center justify-between">
              <p className="label-mono">Athlete profile</p>
              <button
                type="button"
                onClick={onClose}
                className="rounded-full border border-[var(--border)] px-3 py-1 font-mono-ui text-[10px] tracking-wider text-[var(--muted2)]"
              >
                Esc · close
              </button>
            </div>

            <div className="crosshair-corner relative rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] p-5">
              <div className="flex items-center gap-3">
                <div className="relative flex h-16 w-16 items-center justify-center rounded-full bg-gradient-to-br from-[var(--accent)] to-[#5a4bff] font-display text-[20px] font-semibold text-white">
                  АС
                  <span className="absolute -bottom-1 -right-1 h-3 w-3 rounded-full border-2 border-[var(--bg2)] bg-[var(--accent2)]" />
                </div>
                <div>
                  <p className="font-display text-[18px] tracking-tight">Айгерим Смагулова</p>
                  <p className="label-mono mt-1">KZ · Almaty · WS</p>
                </div>
              </div>
            </div>

            <BWFRankCard />

            <section className="grid grid-cols-2 gap-2">
              {stats.map((s) => (
                <div key={s.label} className="rounded-xl border border-[var(--border)] bg-[var(--surface-2)] p-3">
                  <p className="label-mono">{s.label}</p>
                  <p className="hero-number mt-2 text-[24px]" style={{ color: s.tone }}>{s.value}</p>
                </div>
              ))}
            </section>

            <section className="min-h-0 flex-1 overflow-y-auto rounded-2xl border border-[var(--border)] bg-[var(--surface-2)] p-4 thin-scrollbar">
              <div className="mb-3 flex items-center justify-between">
                <p className="font-display text-[13px] tracking-tight">Связи</p>
                <button
                  type="button"
                  className="rounded-full border border-[var(--accent2)] bg-[rgba(184,255,107,0.1)] px-3 py-1 font-mono-ui text-[10px] tracking-wider text-[var(--accent2)]"
                >
                  + Добавить
                </button>
              </div>
              <div className="space-y-2">
                {connections.map((user) => (
                  <div key={user.name} className="flex items-center gap-3 rounded-lg border border-[var(--border)] bg-[var(--surface-1)] p-2.5">
                    <div className="flex h-9 w-9 items-center justify-center rounded-full bg-[var(--bg4)] font-display text-[12px]">{user.initials}</div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-display text-[12px]">{user.name}</p>
                      <p className="label-mono mt-0.5">BWF #{user.rank}</p>
                    </div>
                    <span className={`h-2 w-2 rounded-full ${user.online ? 'bg-[var(--accent2)]' : 'bg-[var(--muted)]'}`} />
                  </div>
                ))}
              </div>
            </section>
          </motion.aside>
        </>
      ) : null}
    </AnimatePresence>
  )
}
