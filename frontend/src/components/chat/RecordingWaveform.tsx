type Props = {
  levels: number[]
  /** When true, add subtle idle motion when mic level is very low */
  fallbackMotion?: boolean
  className?: string
}

const BAR_COUNT = 28

export const RecordingWaveform = ({
  levels,
  fallbackMotion = false,
  className = '',
}: Props) => {
  const bars =
    levels.length >= BAR_COUNT
      ? levels.slice(0, BAR_COUNT)
      : [
          ...levels,
          ...Array.from({ length: BAR_COUNT - levels.length }, () => 0.15),
        ]

  return (
    <div
      className={`flex min-w-0 flex-1 items-center justify-center gap-[3px] ${className}`}
      role="img"
      aria-label="Уровень звука микрофона"
    >
      {bars.map((level, i) => {
        const h = 4 + level * 22
        return (
          <span
            key={i}
            className={`w-[3px] shrink-0 rounded-full bg-[var(--accent3)] transition-[height] duration-75 ease-out ${
              fallbackMotion ? 'recording-bar-idle' : ''
            }`}
            style={{
              height: `${h}px`,
              opacity: 0.45 + level * 0.55,
              animationDelay: fallbackMotion ? `${(i % 7) * 0.08}s` : undefined,
            }}
          />
        )
      })}
    </div>
  )
}

export const idleWaveformLevels = (): number[] =>
  Array.from({ length: BAR_COUNT }, (_, i) => 0.18 + 0.08 * Math.sin(i * 0.55))
