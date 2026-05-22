import { useMemo, useState } from 'react'
import { confirmSchedule } from '../api/schedule'
import type { ScheduleItem } from '../types'

const initialSchedule: ScheduleItem[] = [
  { id: 's1', day: 'MON 28', time: '09:00', name: 'Power Endurance Block', type: 'TRAINING', intensity: 4 },
  { id: 's2', day: 'MON 28', time: '14:30', name: 'Video Tactical Review', type: 'STUDY' },
  { id: 's3', day: 'TUE 29', time: '08:30', name: 'Active Recovery Pool', type: 'RECOVERY' },
  { id: 's4', day: 'WED 30', time: '18:00', name: 'League Match vs Dynamo', type: 'MATCH' },
  { id: 's5', day: 'THU 01', time: '12:00', name: 'AI Added: Reaction Ladder', type: 'TRAINING', intensity: 3, aiAdded: true },
]

export const useSchedule = () => {
  const [items] = useState<ScheduleItem[]>(initialSchedule)
  const [isConfirming, setIsConfirming] = useState(false)

  const confirm = async () => {
    setIsConfirming(true)
    try {
      await confirmSchedule('draft-week-1')
    } finally {
      setIsConfirming(false)
    }
  }

  return useMemo(
    () => ({
      items,
      confirm,
      isConfirming,
    }),
    [items, isConfirming],
  )
}
