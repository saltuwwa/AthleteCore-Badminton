import type { ScheduleItem as ScheduleItemType } from '../../types'
import { ConfirmPlanButton } from './ConfirmPlanButton'
import { ScheduleItem } from './ScheduleItem'

export const WeeklyPlan = ({
  items,
  onConfirm,
  isConfirming,
}: {
  items: ScheduleItemType[]
  onConfirm: () => void
  isConfirming?: boolean
}) => {
  const grouped = items.reduce<Record<string, ScheduleItemType[]>>((acc, item) => {
    acc[item.day] ??= []
    acc[item.day].push(item)
    return acc
  }, {})

  return (
    <div className="h-full overflow-y-auto px-3 py-4 thin-scrollbar">
      <h2 className="font-mono-ui text-[12px] text-[var(--muted)]">Weekly Schedule - AI Draft</h2>
      <div className="mt-4 space-y-4">
        {Object.entries(grouped).map(([day, dayItems]) => (
          <section key={day}>
            <p className="font-mono-ui mb-2 text-[9px] text-[var(--muted)]">{day}</p>
            <div className="space-y-2">
              {dayItems.map((item) => (
                <ScheduleItem key={item.id} item={item} />
              ))}
            </div>
          </section>
        ))}
      </div>
      <ConfirmPlanButton onClick={onConfirm} disabled={isConfirming} />
    </div>
  )
}
