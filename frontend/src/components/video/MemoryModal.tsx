import { motion } from 'framer-motion'

type Props = {
  open: boolean
  onClose: () => void
}

export const MemoryModal = ({ open, onClose }: Props) => {
  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-labelledby="memory-modal-title"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96, y: 8 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        className="w-full max-w-md rounded-2xl border border-[var(--border)] bg-[var(--bg2)] p-6 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="memory-modal-title" className="font-display text-[20px] tracking-tight">
          Как работает память?
        </h2>
        <p className="mt-3 text-[13px] leading-relaxed text-[var(--muted2)]">
          AthleteCore запоминает только спортивные паттерны: ошибки, прогресс, рекомендации и
          важные события. Это помогает сравнивать новые игры с прошлыми.
        </p>
        <button
          type="button"
          onClick={onClose}
          className="mt-6 w-full rounded-xl bg-[var(--accent)] py-2.5 text-[13px] font-semibold text-white transition hover:brightness-110"
        >
          Понятно
        </button>
      </motion.div>
    </div>
  )
}
