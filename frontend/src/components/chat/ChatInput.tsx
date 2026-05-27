import { useEffect, useRef, useState } from 'react'
import { apiClient } from '../../api/client'
import { uploadDocument, type DetectedDocType } from '../../api/documents'
import { useVoiceRecorder } from '../../hooks/useVoiceRecorder'
import { DocumentCard } from './DocumentCard'
import { MicIcon } from '../ui/MicIcon'

const suggestions = [
  'Разбери ошибки 2-го сета',
  'Сгенерируй план восстановления',
  'Сравни с матчем 15 апр',
]

type PendingDoc = {
  documentId: string
  filename: string
  detectedType: DetectedDocType
}

type Props = {
  onSend: (text: string) => void
  onVoiceTranscript?: (text: string) => void
  onDocumentResult?: (message: string, notice?: string | null) => void
  isSending?: boolean
  needsMemory?: boolean | null
  autoSendAfterVoice?: boolean
}

export const ChatInput = ({
  onSend,
  onVoiceTranscript,
  onDocumentResult,
  isSending = false,
  needsMemory = null,
  autoSendAfterVoice = false,
}: Props) => {
  const [text, setText] = useState('')
  const [backendOk, setBackendOk] = useState<boolean | null>(null)
  const [pendingDoc, setPendingDoc] = useState<PendingDoc | null>(null)
  const [docBusy, setDocBusy] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const voice = useVoiceRecorder()

  useEffect(() => {
    let cancelled = false
    const check = async () => {
      try {
        const { data } = await apiClient.get<{ status?: string }>('/health', { timeout: 5000 })
        if (!cancelled) setBackendOk(data?.status === 'ok')
      } catch {
        if (!cancelled) setBackendOk(false)
      }
    }
    check()
    const id = window.setInterval(check, 15_000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [])

  const submit = () => {
    const trimmed = text.trim()
    if (!trimmed || isSending) return
    onSend(trimmed)
    setText('')
  }

  const handleMic = async () => {
    if (voice.isRecording) {
      const transcript = await voice.stopRecording()
      if (transcript) {
        setText(transcript)
        onVoiceTranscript?.(transcript)
        if (autoSendAfterVoice) onSend(transcript)
      }
      return
    }
    await voice.toggleRecording()
  }

  const onFilePicked = async (file: File) => {
    setUploadError(null)
    setDocBusy(true)
    try {
      const res = await uploadDocument(file)
      setPendingDoc({
        documentId: res.document_id,
        filename: res.filename,
        detectedType: res.detected_type,
      })
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : 'Не удалось загрузить файл')
    } finally {
      setDocBusy(false)
    }
  }

  const memoryLabel = needsMemory === null ? '—' : needsMemory ? 'LTM ON' : 'LTM OFF'
  const micBusy = voice.isRecording || voice.isTranscribing
  const busy = isSending || micBusy || docBusy

  return (
    <div className="crosshair-corner relative rounded-2xl border border-[var(--border-strong)] bg-[var(--surface-glass)] p-4 backdrop-blur-md">
      <div className="flex items-center justify-between gap-3">
        <p className="label-mono">Ask Analyst · Chat</p>
        <div className="flex items-center gap-3">
          <span
            className="label-mono rounded-full border border-[var(--border)] px-2 py-0.5 text-[9px]"
            style={{
              color: needsMemory ? 'var(--accent2)' : needsMemory === false ? 'var(--muted)' : 'var(--muted2)',
            }}
          >
            Memory {memoryLabel}
          </span>
          <span
            className={`h-1.5 w-1.5 rounded-full pulse-dot ${
              backendOk === false ? 'bg-[var(--accent3)]' : 'bg-[var(--accent2)]'
            }`}
          />
        </div>
      </div>

      {pendingDoc ? (
        <div className="mt-3">
          <DocumentCard
            documentId={pendingDoc.documentId}
            filename={pendingDoc.filename}
            detectedType={pendingDoc.detectedType}
            onBusyChange={setDocBusy}
            onRemove={() => setPendingDoc(null)}
            onResult={(msg, notice) => {
              onDocumentResult?.(notice ? `${notice}\n\n${msg}` : msg)
            }}
          />
        </div>
      ) : null}

      {uploadError ? <p className="mt-2 text-[11px] text-[var(--accent3)]">{uploadError}</p> : null}

      {voice.isRecording ? (
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-[rgba(255,107,138,0.25)] bg-[rgba(255,107,138,0.08)] px-3 py-2">
          <span className="h-2 w-2 rounded-full bg-[var(--accent3)] pulse-dot" />
          <span className="font-mono-ui text-[11px] text-[var(--accent3)]">Запись…</span>
        </div>
      ) : null}

      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault()
            submit()
          }
        }}
        rows={2}
        disabled={busy}
        placeholder="Матч, тренировка или турнирный файл…"
        className="font-display mt-3 w-full resize-none bg-transparent text-[14px] leading-relaxed text-[var(--text-primary)] outline-none placeholder:text-[var(--muted)] disabled:opacity-50"
      />

      <input
        ref={fileRef}
        type="file"
        className="hidden"
        accept=".pdf,.docx,.xlsx,.xls,.csv,.png,.jpg,.jpeg,.webp"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) void onFilePicked(f)
          e.target.value = ''
        }}
      />

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {suggestions.map((s) => (
          <button
            key={s}
            type="button"
            disabled={busy}
            onClick={() => setText(s)}
            className="rounded-full border border-[var(--border)] bg-[var(--bg3)] px-3 py-1 text-[11px] text-[var(--muted2)] hover:border-[var(--accent)] disabled:opacity-40"
          >
            {s}
          </button>
        ))}

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            disabled={busy}
            onClick={() => fileRef.current?.click()}
            className="flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--bg3)] text-[14px] disabled:opacity-40"
            title="Прикрепить документ"
            aria-label="Прикрепить документ"
          >
            📎
          </button>
          <button
            type="button"
            disabled={isSending || voice.isTranscribing}
            onClick={handleMic}
            className={`flex h-9 w-9 items-center justify-center rounded-full border ${
              voice.isRecording
                ? 'border-[var(--accent3)] bg-[rgba(255,107,138,0.12)] text-[var(--accent3)]'
                : 'border-[var(--border)] bg-[var(--bg3)]'
            }`}
            aria-label="Голос"
          >
            <MicIcon size={17} />
          </button>
          <button
            type="button"
            disabled={busy || !text.trim()}
            onClick={submit}
            className="rounded-full bg-[var(--accent)] px-5 py-2 font-display text-[12px] font-semibold text-white disabled:opacity-40"
          >
            {isSending ? '…' : 'Отправить →'}
          </button>
        </div>
      </div>
    </div>
  )
}
