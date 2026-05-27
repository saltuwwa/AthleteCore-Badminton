import { Link } from 'react-router-dom'

const PlusIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden>
    <path
      d="M12 5v14M5 12h14"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
    />
  </svg>
)

/** ChatGPT-style entry bar on Home — click opens /chat */
export const ChatEntryBar = () => {
  return (
    <div className="shrink-0 border-t border-[var(--border)] bg-[color-mix(in_srgb,var(--bg-deep)_85%,transparent)] px-8 py-5 backdrop-blur-md">
      <Link
        to="/chat"
        className="group mx-auto flex max-w-3xl items-center gap-3 rounded-[28px] border border-[var(--border-strong)] bg-[var(--surface-glass)] px-4 py-3.5 shadow-[0_0_0_1px_rgba(48,109,255,0.06),0_8px_32px_-12px_rgba(0,0,0,0.5)] transition-all hover:border-[color-mix(in_srgb,var(--accent)_35%,var(--border-strong))] hover:shadow-[0_0_24px_-8px_rgba(48,109,255,0.35)]"
      >
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--bg3)] text-[var(--muted2)] transition-colors group-hover:border-[var(--accent)] group-hover:text-[var(--accent)]">
          <PlusIcon />
        </span>
        <span className="flex-1 text-left font-display text-[14px] text-[var(--muted2)] transition-colors group-hover:text-[var(--text-soft)]">
          Спросите AthleteCore
        </span>
        <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[var(--text-primary)] text-[var(--bg-deep)] opacity-90 transition-opacity group-hover:opacity-100">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden>
            <path
              d="M12 19V5M12 5l-6 6M12 5l6 6"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
      </Link>
    </div>
  )
}
