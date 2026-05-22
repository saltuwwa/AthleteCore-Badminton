import { useCallback, useState } from 'react'
import { seedScheduleEvents } from '../data/scheduleData'
import type { ScheduleEvent } from '../types/schedule'

export type NewEventInput = Omit<ScheduleEvent, 'id'>

export const useScheduleEvents = () => {
  const [events, setEvents] = useState<ScheduleEvent[]>(seedScheduleEvents)

  const addEvent = useCallback((input: NewEventInput) => {
    setEvents((prev) => [
      ...prev,
      { ...input, id: `local-${Date.now()}-${Math.random().toString(16).slice(2, 6)}` },
    ])
  }, [])

  const removeEvent = useCallback((id: string) => {
    setEvents((prev) => prev.filter((e) => e.id !== id))
  }, [])

  return { events, addEvent, removeEvent }
}
