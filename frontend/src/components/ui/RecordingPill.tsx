export const RecordingPill = ({ text }: { text: string }) => {
  return (
    <div className="inline-flex items-center gap-2 rounded-lg border border-[rgba(255,127,95,0.2)] bg-[rgba(255,127,95,0.12)] px-3 py-1">
      <span className="pulse-dot h-2 w-2 rounded-full bg-[var(--accent3)]" />
      <span className="font-mono-ui text-[9px] text-[var(--accent3)]">{text}</span>
    </div>
  )
}
