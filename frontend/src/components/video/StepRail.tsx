const STEPS = ['Загрузка', 'Игроки', 'Результат'] as const

export const StepRail = ({ current }: { current: 0 | 1 | 2 }) => (
  <div className="flex items-center gap-2">
    {STEPS.map((label, i) => {
      const active = i === current
      const done = i < current
      return (
        <div key={label} className="flex items-center gap-2">
          <div
            className={`flex h-7 w-7 items-center justify-center rounded-full font-mono-ui text-[11px] font-semibold ${
              active
                ? 'bg-[var(--accent)] text-white'
                : done
                  ? 'bg-[var(--accent2)]/20 text-[var(--accent2)]'
                  : 'bg-[var(--surface-2)] text-[var(--muted)]'
            }`}
          >
            {done ? '✓' : i + 1}
          </div>
          <span
            className={`hidden text-[12px] sm:inline ${
              active ? 'text-[var(--text-primary)]' : 'text-[var(--muted)]'
            }`}
          >
            {label}
          </span>
          {i < STEPS.length - 1 && (
            <div className="mx-1 h-px w-6 bg-[var(--border)] sm:w-10" />
          )}
        </div>
      )
    })}
  </div>
)
