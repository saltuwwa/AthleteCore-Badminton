import { ErrorTag } from '../ui/ErrorTag'

export const AnalysisCard = ({
  level,
  text,
  pattern,
}: {
  level: 'HIGH' | 'MED' | 'LOW'
  text: string
  pattern: string
}) => {
  return (
    <div className="mt-2 rounded-[10px] border border-[var(--border)] bg-[var(--bg3)] p-3">
      <p className="font-mono-ui text-[10px] text-[var(--muted)]">Разбор ошибок</p>
      <div className="mt-2 flex gap-2">
        <ErrorTag level={level} />
      </div>
      <p className="font-display mt-2 text-[12px] text-[var(--text)]">{text}</p>
      <p className="font-mono-ui mt-2 text-[10px] text-[var(--accent)]">{pattern}</p>
    </div>
  )
}
