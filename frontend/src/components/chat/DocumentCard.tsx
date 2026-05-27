import {
  analyzeDocument,
  documentTypeLabel,
  type DetectedDocType,
  type DocumentAction,
} from '../../api/documents'

const ACTIONS: { id: DocumentAction; label: string }[] = [
  { id: 'parse_results', label: 'Разобрать результаты' },
  { id: 'find_my_matches', label: 'Найти мои матчи' },
  { id: 'compare_past', label: 'Сравнить с прошлым турниром' },
]

type Props = {
  documentId: string
  filename: string
  detectedType: DetectedDocType
  onResult: (message: string, notice?: string | null) => void
  onBusyChange?: (busy: boolean) => void
  onRemove: () => void
}

export const DocumentCard = ({
  documentId,
  filename,
  detectedType,
  onResult,
  onBusyChange,
  onRemove,
}: Props) => {
  const run = async (action: DocumentAction) => {
    onBusyChange?.(true)
    try {
      const res = await analyzeDocument({ document_id: documentId, action })
      onResult(res.assistant_message, res.structured.security_notice)
    } catch (e) {
      onResult(e instanceof Error ? e.message : 'Ошибка разбора документа')
    } finally {
      onBusyChange?.(false)
    }
  }

  return (
    <div className="rounded-xl border border-[var(--border)] bg-[var(--bg3)] px-3 py-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate font-mono-ui text-[11px] text-[var(--text-primary)]">{filename}</p>
          <p className="text-[10px] text-[var(--muted)]">{documentTypeLabel(detectedType)}</p>
        </div>
        <button
          type="button"
          onClick={onRemove}
          className="shrink-0 text-[var(--muted)] hover:text-[var(--accent3)]"
          aria-label="Убрать файл"
        >
          ×
        </button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {ACTIONS.map((a) => (
          <button
            key={a.id}
            type="button"
            onClick={() => void run(a.id)}
            className="rounded-lg border border-[var(--border)] bg-[var(--surface-2)] px-2.5 py-1 text-[10px] text-[var(--muted2)] transition hover:border-[var(--accent)] hover:text-[var(--text-primary)]"
          >
            {a.label}
          </button>
        ))}
      </div>
    </div>
  )
}
