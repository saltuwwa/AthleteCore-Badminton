const items = [
  { day: 'Пн', time: '09:00', title: 'Скоростная работа', ai: false },
  { day: 'Вт', time: '11:30', title: 'Видеоразбор сетки', ai: true },
  { day: 'Ср', time: '18:00', title: 'Матч-спарринг', ai: false },
  { day: 'Чт', time: '08:30', title: 'Восстановление', ai: true },
]

export const ScheduleGrid = () => {
  return (
    <section className="grid grid-cols-2 gap-2">
      {items.map((item) => (
        <article
          key={`${item.day}-${item.time}`}
          className={`rounded-xl border p-3 ${item.ai ? 'border-[rgba(124,107,255,0.45)] bg-[rgba(124,107,255,0.08)]' : 'border-[var(--border)] bg-[var(--bg2)]'}`}
        >
          <p className="text-[11px] text-[var(--muted)]">{item.day} · {item.time}</p>
          <p className="mt-1 text-[13px] text-[var(--text-primary)]">{item.title}</p>
          {item.ai ? <p className="mt-2 text-[10px] text-[var(--accent)]">AI-ADDED</p> : null}
        </article>
      ))}
    </section>
  )
}
