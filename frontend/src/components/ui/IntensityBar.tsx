export const IntensityBar = ({ level = 0 }: { level?: number }) => {
  return (
    <div className="flex items-center gap-1">
      {Array.from({ length: 5 }).map((_, idx) => (
        <span
          key={idx}
          className="h-2 w-2 rounded-full"
          style={{ background: idx < level ? 'var(--accent)' : 'var(--border2)' }}
        />
      ))}
    </div>
  )
}
