import { useEffect, useState } from 'react'
import { apiClient } from '../../api/client'
import { useVoiceRecorder } from '../../hooks/useVoiceRecorder'
import { MicIcon } from '../ui/MicIcon'

const suggestions = [
  'Разбери ошибки 2-го сета',
  'Сгенерируй план восстановления',
  'Сравни с матчем 15 апр',
]

type Props = {
  onSend: (text: string) => void
  onVoiceTranscript?: (text: string) => void
  isSending?: boolean
  needsMemory?: boolean | null
  /** false = только транскрипт в поле и чат-черновик, без авто-отправки */
  autoSendAfterVoice?: boolean
}

export const ChatInput = ({
  onSend,
  onVoiceTranscript,
  isSending = false,
  needsMemory = null,
  autoSendAfterVoice = false,
}: Props) => {
  const [text, setText] = useState('')
  const [backendOk, setBackendOk] = useState<boolean | null>(null)
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
        if (autoSendAfterVoice) {
          onSend(transcript)
        }
      }
      return
    }
    await voice.toggleRecording()
  }

  const memoryLabel = needsMemory === null ? '—' : needsMemory ? 'LTM ON' : 'LTM OFF'
  const micBusy = voice.isRecording || voice.isTranscribing
  const busy = isSending || micBusy

  return (
    <div className="crosshair-corner relative rounded-2xl border border-[var(--border-strong)] bg-[var(--surface-glass)] p-4 backdrop-blur-md">
      <div className="flex items-center justify-between gap-3">
        <p className="label-mono">Ask Analyst · LangGraph + Whisper</p>
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
          <span
            className={`label-mono ${
              backendOk === false ? 'text-[var(--accent3)]' : 'text-[var(--accent2)]'
            }`}
          >
            {voice.isTranscribing
              ? 'WHISPER'
              : isSending
                ? 'SENDING'
                : backendOk === false
                  ? 'OFFLINE'
                  : backendOk === null
                    ? '…'
                    : 'CONNECTED'}
          </span>
        </div>
      </div>

      {voice.isRecording ? (
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-[rgba(255,107,138,0.25)] bg-[rgba(255,107,138,0.08)] px-3 py-2">
          <span className="h-2 w-2 rounded-full bg-[var(--accent3)] pulse-dot" />
          <span className="font-mono-ui text-[11px] text-[var(--accent3)]">
            REC {Math.floor(voice.seconds / 60)}:{String(voice.seconds % 60).padStart(2, '0')} · нажми микрофон, чтобы остановить
          </span>
        </div>
      ) : null}

      {voice.transcriptNote && !voice.isRecording ? (
        <p className="label-mono mt-2 text-[var(--accent2)]">{voice.transcriptNote}</p>
      ) : null}

      {voice.error ? (
        <p className="mt-2 text-[11px] text-[var(--accent3)]">{voice.error}</p>
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
        placeholder="Запиши голос или введи текст — после записи проверь черновик в чате и нажми «Отправить»"
        className="font-display mt-3 w-full resize-none bg-transparent text-[14px] leading-relaxed text-[var(--text-primary)] outline-none placeholder:text-[var(--muted)] disabled:opacity-50"
      />

      <div className="mt-3 flex flex-wrap items-center gap-2">
        {suggestions.map((s) => (
          <button
            key={s}
            type="button"
            disabled={busy}
            onClick={() => setText(s)}
            className="rounded-full border border-[var(--border)] bg-[var(--bg3)] px-3 py-1 text-[11px] text-[var(--muted2)] transition-colors hover:border-[var(--accent)] hover:text-[var(--accent-strong)] disabled:opacity-40"
          >
            {s}
          </button>
        ))}

        <div className="ml-auto flex items-center gap-2">
          <button
            type="button"
            disabled={isSending || voice.isTranscribing}
            onClick={handleMic}
            className={`relative flex h-9 w-9 items-center justify-center rounded-full border ${
              voice.isRecording
                ? 'border-[var(--accent3)] bg-[rgba(255,107,138,0.12)] text-[var(--accent3)]'
                : 'border-[var(--border)] bg-[var(--bg3)] text-[var(--text-soft)]'
            }`}
            title={voice.isRecording ? 'Остановить и транскрибировать' : 'Записать голосовой лог'}
            aria-label={voice.isRecording ? 'Остановить запись' : 'Записать голосовой лог'}
          >
            {voice.isRecording ? <span className="pulse-ring" style={{ color: 'var(--accent3)' }} /> : null}
            <MicIcon size={17} className="relative z-[1]" />
          </button>
          <button
            type="button"
            className="flex h-9 w-9 items-center justify-center rounded-full border border-[var(--border)] bg-[var(--bg3)] text-[14px]"
            aria-label="Прикрепить"
          >
            <span aria-hidden>📎</span>
          </button>
          <button
            type="button"
            disabled={busy || !text.trim()}
            onClick={submit}
            className="glow-breathe rounded-full bg-[var(--accent)] px-5 py-2 font-display text-[12px] font-semibold tracking-wide text-white disabled:opacity-40"
          >
            {isSending ? '…' : 'Отправить →'}
          </button>
        </div>
      </div>
    </div>
  )
}
