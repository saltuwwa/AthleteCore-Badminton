import { useCallback, useEffect, useRef, useState } from 'react'
import { apiClient } from '../../api/client'
import { fetchChatSuggestions } from '../../api/chat'
import { uploadDocument, type DetectedDocType } from '../../api/documents'
import { useVoiceRecorder } from '../../hooks/useVoiceRecorder'
import { DocumentCard } from './DocumentCard'
import { MicIcon } from '../ui/MicIcon'
import { RecordingWaveform } from './RecordingWaveform'

const DEFAULT_SUGGESTIONS = [
  'Разбери мою последнюю тренировку',
  'Помоги найти ошибки в матче',
  'Составь план восстановления',
  'Что улучшить перед следующим матчем?',
]

const TEXTAREA_MIN_PX = 40
const TEXTAREA_MAX_PX = 220

type PendingDoc = {
  documentId: string
  filename: string
  detectedType: DetectedDocType
}

type Props = {
  onSend: (text: string) => void
  onDocumentResult?: (message: string, notice?: string | null) => void
  isSending?: boolean
  needsMemory?: boolean | null
  autoSendAfterVoice?: boolean
  prefill?: string | null
  onPrefillApplied?: () => void
}

export const ChatInput = ({
  onSend,
  onDocumentResult,
  isSending = false,
  needsMemory = null,
  autoSendAfterVoice = false,
  prefill = null,
  onPrefillApplied,
}: Props) => {
  const [text, setText] = useState('')
  const [suggestions, setSuggestions] = useState<string[]>(DEFAULT_SUGGESTIONS)
  const [backendOk, setBackendOk] = useState<boolean | null>(null)
  const [pendingDoc, setPendingDoc] = useState<PendingDoc | null>(null)
  const [docBusy, setDocBusy] = useState(false)
  const [uploadError, setUploadError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const voice = useVoiceRecorder()

  const adjustTextareaHeight = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = 'auto'
    const next = Math.min(Math.max(el.scrollHeight, TEXTAREA_MIN_PX), TEXTAREA_MAX_PX)
    el.style.height = `${next}px`
    el.style.overflowY = el.scrollHeight > TEXTAREA_MAX_PX ? 'auto' : 'hidden'
  }, [])

  const resetTextareaHeight = useCallback(() => {
    const el = textareaRef.current
    if (!el) return
    el.style.height = `${TEXTAREA_MIN_PX}px`
    el.style.overflowY = 'hidden'
  }, [])

  useEffect(() => {
    if (!voice.isRecording) adjustTextareaHeight()
  }, [text, adjustTextareaHeight, voice.isRecording])

  useEffect(() => {
    if (!prefill) return
    setText(prefill)
    onPrefillApplied?.()
    adjustTextareaHeight()
  }, [prefill, onPrefillApplied, adjustTextareaHeight])

  useEffect(() => {
    let cancelled = false
    fetchChatSuggestions()
      .then((items) => {
        if (!cancelled && items.length) setSuggestions(items)
      })
      .catch(() => {
        if (!cancelled) setSuggestions(DEFAULT_SUGGESTIONS)
      })
    return () => {
      cancelled = true
    }
  }, [])

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
    resetTextareaHeight()
  }

  const handleMic = async () => {
    if (voice.isRecording) {
      const transcript = await voice.stopRecording()
      if (transcript) {
        setText(transcript)
        adjustTextareaHeight()
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

  const formatRecTime = (s: number) =>
    `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`

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

      <div
        className={`mt-3 rounded-xl border bg-[var(--bg3)]/40 p-2 transition-colors focus-within:border-[rgba(200,255,95,0.2)] ${
          voice.isRecording
            ? 'border-[rgba(255,107,138,0.35)] bg-[rgba(255,107,138,0.06)]'
            : 'border-[var(--border)]'
        }`}
      >
        <div className="relative min-h-[44px]">
          {voice.isRecording ? (
            <div className="flex min-h-[44px] w-full min-w-0 items-center gap-2.5 pb-11 pr-1 pl-1 pt-1">
              <div className="flex shrink-0 items-center gap-1.5">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-[var(--accent3)] opacity-60" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-[var(--accent3)]" />
                </span>
                <span className="font-mono-ui whitespace-nowrap text-[11px] text-[var(--accent3)]">
                  Запись…
                </span>
                <span className="font-mono-ui hidden text-[10px] text-[var(--muted2)] sm:inline">
                  {formatRecTime(voice.seconds)}
                </span>
              </div>
              <RecordingWaveform
                levels={voice.audioLevels}
                fallbackMotion={voice.useLevelFallback}
              />
            </div>
          ) : (
            <textarea
              ref={textareaRef}
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  submit()
                }
              }}
              rows={1}
              disabled={busy}
              placeholder="Матч, тренировка или турнирный файл…"
              style={{ height: TEXTAREA_MIN_PX }}
              className="font-display block w-full min-w-0 resize-none overflow-x-hidden bg-transparent px-2 pb-11 pt-1.5 text-[14px] leading-relaxed text-[var(--text-primary)] outline-none placeholder:text-[var(--muted)] disabled:opacity-50"
            />
          )}

          <div className="pointer-events-none absolute inset-x-2 bottom-2 flex items-center justify-end gap-1.5 sm:gap-2">
            <div className="pointer-events-auto flex items-center gap-1.5 sm:gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => fileRef.current?.click()}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--bg3)] text-[14px] disabled:opacity-40"
                title="Прикрепить документ"
                aria-label="Прикрепить документ"
              >
                📎
              </button>
              <button
                type="button"
                disabled={isSending || voice.isTranscribing}
                onClick={handleMic}
                className={`relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full border ${
                  voice.isRecording
                    ? 'border-[var(--accent3)] bg-[rgba(255,107,138,0.18)] text-[var(--accent3)] shadow-[0_0_0_3px_rgba(255,107,138,0.12)]'
                    : 'border-[var(--border)] bg-[var(--bg3)]'
                }`}
                aria-label={voice.isRecording ? 'Остановить запись' : 'Голос'}
              >
                {voice.isRecording ? (
                  <span className="h-3 w-3 rounded-sm bg-[var(--accent3)]" />
                ) : (
                  <MicIcon size={17} />
                )}
              </button>
              <button
                type="button"
                disabled={busy || !text.trim() || voice.isRecording}
                onClick={submit}
                className="shrink-0 rounded-full bg-[var(--accent)] px-3 py-2 font-display text-[11px] font-semibold text-white disabled:opacity-40 sm:px-5 sm:text-[12px]"
              >
                {isSending ? '…' : (
                  <>
                    <span className="sm:hidden">→</span>
                    <span className="hidden sm:inline">Отправить →</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {voice.isTranscribing ? (
          <div className="mt-2 flex items-center gap-2 border-t border-[var(--border)]/60 px-1 pt-2">
            <span className="inline-flex items-center gap-0.5">
              <span className="pulse-dot h-1 w-1 rounded-full bg-[var(--muted2)]" />
              <span className="pulse-dot h-1 w-1 rounded-full bg-[var(--muted2)] [animation-delay:0.2s]" />
              <span className="pulse-dot h-1 w-1 rounded-full bg-[var(--muted2)] [animation-delay:0.4s]" />
            </span>
            <span className="font-mono-ui text-[10px] text-[var(--muted2)]">Транскрибируется…</span>
          </div>
        ) : null}

        {voice.error && !voice.isTranscribing && !voice.isRecording ? (
          <p className="mt-1 px-1 text-[10px] text-[var(--accent3)]">{voice.error}</p>
        ) : null}
      </div>

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
      </div>
    </div>
  )
}
