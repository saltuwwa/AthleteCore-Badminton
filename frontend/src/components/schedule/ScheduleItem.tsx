import type { ScheduleItem as ScheduleItemType } from '../../types'
import { IntensityBar } from '../ui/IntensityBar'

const tagColor = (type: ScheduleItemType['type']) =>
  ({
    TRAINING: 'text-[var(--accent)] bg-[rgba(200,255,95,0.15)]',
    RECOVERY: 'text-[var(--accent2)] bg-[rgba(95,159,255,0.15)]',
    STUDY: 'text-[var(--amber)] bg-[rgba(255,200,60,0.18)]',
    MATCH: 'text-[var(--accent3)] bg-[rgba(255,127,95,0.18)]',
  })[type]

export const ScheduleItem = ({ item }: { item: ScheduleItemType }) => {
  return (
    <div
      className={`rounded-lg border bg-[var(--bg3)] p-2 ${
        item.aiAdded
          ? 'border-[rgba(200,255,95,0.2)] bg-[rgba(200,255,95,0.03)]'
          : 'border-[var(--border)]'
      }`}
    >
      <div className="flex gap-3">
        <span className="font-mono-ui text-[10px] text-[var(--muted)]">{item.time}</span>
        <div className="min-w-0">
          <p className="font-display text-[12px] font-semibold text-[var(--text)]">{item.name}</p>
          <div className="mt-1 flex items-center gap-2">
            <span className={`font-mono-ui rounded px-2 py-[2px] text-[9px] ${tagColor(item.type)}`}>{item.type}</span>
            {item.aiAdded ? (
              <span className="font-mono-ui rounded border border-[rgba(200,255,95,0.35)] px-2 py-[2px] text-[9px] text-[var(--accent)]">
                AI ADDED
              </span>
            ) : null}
          </div>
          {item.type === 'TRAINING' ? <div className="mt-2"><IntensityBar level={item.intensity} /></div> : null}
        </div>
      </div>
    </div>
  )
}
