import { useSchedule } from '../../hooks/useSchedule'
import { WeeklyPlan } from '../schedule/WeeklyPlan'

export const RightPanel = () => {
  const { items, confirm, isConfirming } = useSchedule()

  return (
    <aside className="h-screen w-[280px] border-l border-[var(--border)] bg-[var(--bg2)]">
      <WeeklyPlan items={items} onConfirm={confirm} isConfirming={isConfirming} />
    </aside>
  )
}
