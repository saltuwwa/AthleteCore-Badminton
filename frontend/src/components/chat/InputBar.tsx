import { useState } from 'react'
import { MicIcon } from '../ui/MicIcon'
import { RecordingPill } from '../ui/RecordingPill'

export const InputBar = ({
  onSend,
  isSending,
}: {
  onSend: (text: string) => Promise<void> | void
  isSending?: boolean
}) => {
  const [text, setText] = useState('')
  const [recording, setRecording] = useState(false)

  const submit = async () => {
    if (!text.trim()) return
    await onSend(text)
    setText('')
  }

  return (
    <div className="space-y-2">
      {recording ? <RecordingPill text="REC 00:32" /> : null}
      <div className="rounded-xl border border-[var(--border2)] bg-[var(--bg2)] p-2 focus-within:border-[rgba(200,255,95,0.25)]">
        <div className="flex items-end gap-2">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={2}
            placeholder="Расскажи о тренировке или матче..."
            className="font-display max-h-24 min-h-8 flex-1 resize-none bg-transparent px-2 py-1 text-[13px] text-[var(--text)] outline-none placeholder:text-[var(--muted)]"
          />
          <button type="button" className="h-8 w-8 rounded-lg border border-[var(--border)] text-[14px]">
            📎
          </button>
          <button
            type="button"
            onClick={() => setRecording((prev) => !prev)}
            className={`flex h-8 w-8 items-center justify-center rounded-lg border ${
              recording
                ? 'pulse-dot border-[var(--accent3)] bg-[rgba(255,127,95,0.15)] text-[var(--accent3)]'
                : 'border-[var(--border)] text-[var(--text-soft)]'
            }`}
            aria-label="Запись голоса"
          >
            <MicIcon size={16} />
          </button>
          <button
            type="button"
            disabled={isSending}
            onClick={submit}
            className="font-display rounded-lg bg-[var(--accent)] px-3 py-2 text-[12px] font-bold tracking-[0.04em] text-[var(--bg)] disabled:opacity-60"
          >
            SEND
          </button>
        </div>
      </div>
    </div>
  )
}
