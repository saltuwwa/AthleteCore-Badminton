import { ErrorTag } from '../ui/ErrorTag'
import type { AnalystStructured, ChatAction } from '../../types'
import { ChatActions } from './ChatActions'

const normalizeRisk = (risk?: string): 'HIGH' | 'MED' | 'LOW' => {
  const r = (risk ?? 'MEDIUM').toUpperCase()
  if (r === 'HIGH') return 'HIGH'
  if (r === 'LOW') return 'LOW'
  return 'MED'
}

export const AnalystReport = ({
  structured,
  intro,
  actions,
  onPrefill,
}: {
  structured: AnalystStructured
  intro?: string
  actions?: ChatAction[]
  onPrefill?: (text: string) => void
}) => {
  const risk = normalizeRisk(structured.recurrence_risk)

  return (
    <div className="mt-2 space-y-3 rounded-[10px] border border-[var(--border)] bg-[var(--bg3)] p-3">
      <p className="font-mono-ui text-[10px] text-[var(--muted)]">Analyst · разбор</p>

      {structured.comparison_label ? (
        <p className="font-mono-ui text-[10px] text-[var(--accent2)]">{structured.comparison_label}</p>
      ) : null}

      {intro?.trim() ? (
        <p className="font-display text-[12px] leading-relaxed text-[var(--text-primary)]">{intro}</p>
      ) : null}

      {structured.summary ? (
        <section>
          <p className="font-mono-ui text-[9px] uppercase tracking-wide text-[var(--muted)]">Краткий вывод</p>
          <p className="font-display mt-1 text-[12px] leading-relaxed text-[var(--text-primary)]">
            {structured.summary}
          </p>
        </section>
      ) : null}

      {structured.improved?.length ? (
        <section>
          <p className="font-mono-ui text-[9px] uppercase tracking-wide text-[var(--accent)]">Что улучшилось</p>
          <ul className="mt-1 list-inside list-disc space-y-0.5 text-[12px] text-[var(--text-primary)]">
            {structured.improved.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {structured.repeated?.length ? (
        <section>
          <p className="font-mono-ui text-[9px] uppercase tracking-wide text-[var(--accent3)]">Что повторилось</p>
          <ul className="mt-1 list-inside list-disc space-y-0.5 text-[12px] text-[var(--text-primary)]">
            {structured.repeated.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </section>
      ) : null}

      {structured.recurrence_risk ? (
        <div className="flex items-center gap-2">
          <p className="font-mono-ui text-[9px] text-[var(--muted)]">Риск повторения</p>
          <ErrorTag level={risk} />
        </div>
      ) : null}

      {structured.next_training ? (
        <section>
          <p className="font-mono-ui text-[9px] uppercase tracking-wide text-[var(--muted2)]">
            Следующая тренировка
          </p>
          <p className="font-display mt-1 text-[12px] text-[var(--text-primary)]">{structured.next_training}</p>
        </section>
      ) : null}

      {structured.errors?.length ? (
        <section className="space-y-2 border-t border-[var(--border)] pt-2">
          {structured.errors.map((e, i) => (
            <div key={`${e.description}-${i}`} className="rounded-lg border border-[var(--border)] bg-[var(--bg2)] p-2">
              <ErrorTag level={normalizeRisk(e.tag)} />
              {e.description ? (
                <p className="font-display mt-1 text-[11px] text-[var(--text-primary)]">{e.description}</p>
              ) : null}
              {e.fix ? <p className="font-mono-ui mt-1 text-[10px] text-[var(--accent)]">{e.fix}</p> : null}
            </div>
          ))}
        </section>
      ) : null}

      {actions?.length ? (
        <div className="border-t border-[var(--border)] pt-2">
          <ChatActions actions={actions} onPrefill={onPrefill} />
        </div>
      ) : null}
    </div>
  )
}
