export type EventType = 'TRAINING' | 'MATCH' | 'RECOVERY' | 'STUDY' | 'GYM' | 'OTHER'

export type ScheduleEvent = {
  id: string
  date: string
  startTime: string
  endTime: string
  title: string
  type: EventType
  intensity?: number
  aiAdded?: boolean
  notes?: string
}

export type ScheduleView = 'month' | 'week' | 'day'

export const EVENT_TYPE_META: Record<EventType, { label: string; color: string; bg: string; border: string }> = {
  TRAINING: { label: 'Тренировка', color: 'var(--accent)', bg: 'rgba(124,107,255,0.18)', border: 'rgba(124,107,255,0.4)' },
  MATCH: { label: 'Матч', color: 'var(--accent3)', bg: 'rgba(255,107,138,0.18)', border: 'rgba(255,107,138,0.4)' },
  RECOVERY: { label: 'Восстановление', color: 'var(--accent2)', bg: 'rgba(184,255,107,0.16)', border: 'rgba(184,255,107,0.35)' },
  STUDY: { label: 'Учёба / разбор', color: '#ffc83c', bg: 'rgba(255,200,60,0.16)', border: 'rgba(255,200,60,0.35)' },
  GYM: { label: 'Зал / ОФП', color: '#5fbcff', bg: 'rgba(95,188,255,0.16)', border: 'rgba(95,188,255,0.35)' },
  OTHER: { label: 'Другое', color: 'var(--muted2)', bg: 'rgba(255,255,255,0.06)', border: 'rgba(255,255,255,0.12)' },
}
