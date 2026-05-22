import { motion } from 'framer-motion'

type SignalItem = {
  label: string
  value: string
  tone?: 'neutral' | 'good' | 'alert' | 'accent'
}

const toneColor = (tone: SignalItem['tone']) => {
  switch (tone) {
    case 'good':
      return 'var(--accent2)'
    case 'alert':
      return 'var(--accent3)'
    case 'accent':
      return 'var(--accent)'
    default:
      return 'var(--text-soft)'
  }
}

export const SignalStrip = ({
  title,
  items,
}: {
  title: string
  items: SignalItem[]
}) => {
  return (
    <motion.section
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3 }}
      className="relative mx-8 mt-4 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--surface-1)]"
    >
      <div className="flex items-center gap-3 border-b border-[var(--border)] px-4 py-2">
        <span className="relative h-2 w-2">
          <span className="absolute inset-0 rounded-full bg-[var(--accent2)]" />
          <span className="pulse-ring" style={{ color: 'var(--accent2)' }} />
        </span>
        <p className="label-mono text-[var(--muted2)]">{title}</p>
      </div>
      <div className="signal-marquee">
        <div className="signal-track">
          {[...items, ...items].map((item, idx) => (
            <div key={`${item.label}-${idx}`} className="signal-pill">
              <span className="font-mono-ui text-[10px] tracking-[0.14em] text-[var(--muted)]">
                {item.label}
              </span>
              <span
                className="font-display ml-2 text-[13px]"
                style={{ color: toneColor(item.tone) }}
              >
                {item.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </motion.section>
  )
}
