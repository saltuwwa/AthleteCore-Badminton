import type { ScheduleEvent } from '../types/schedule'

const today = new Date()
const iso = (d: Date) => d.toISOString().slice(0, 10)
const offsetDay = (n: number) => {
  const d = new Date(today)
  d.setDate(today.getDate() + n)
  return iso(d)
}

export const seedScheduleEvents: ScheduleEvent[] = [
  { id: 'e1', date: offsetDay(-2), startTime: '08:00', endTime: '09:30', title: 'Кардио + разминка', type: 'TRAINING', intensity: 2 },
  { id: 'e2', date: offsetDay(-1), startTime: '11:00', endTime: '12:30', title: 'Скоростная работа', type: 'TRAINING', intensity: 4 },
  { id: 'e3', date: offsetDay(-1), startTime: '18:00', endTime: '19:00', title: 'Видеоразбор сетки', type: 'STUDY' },
  { id: 'e4', date: offsetDay(0), startTime: '09:00', endTime: '10:30', title: 'Технический блок', type: 'TRAINING', intensity: 3, aiAdded: true },
  { id: 'e5', date: offsetDay(0), startTime: '14:00', endTime: '15:00', title: 'Восстановление / бассейн', type: 'RECOVERY' },
  { id: 'e6', date: offsetDay(0), startTime: '19:30', endTime: '20:30', title: 'ОФП в зале', type: 'GYM', intensity: 3 },
  { id: 'e7', date: offsetDay(1), startTime: '10:00', endTime: '12:00', title: 'Спарринг с тренером', type: 'TRAINING', intensity: 5 },
  { id: 'e8', date: offsetDay(2), startTime: '17:00', endTime: '20:00', title: 'Турнир Almaty Open · 1/16', type: 'MATCH', intensity: 5 },
  { id: 'e9', date: offsetDay(3), startTime: '09:00', endTime: '10:00', title: 'Лёгкий бег', type: 'RECOVERY', aiAdded: true },
  { id: 'e10', date: offsetDay(3), startTime: '15:00', endTime: '16:30', title: 'Тактический разбор', type: 'STUDY' },
  { id: 'e11', date: offsetDay(4), startTime: '11:00', endTime: '13:00', title: 'Реакция и работа ног', type: 'TRAINING', intensity: 4, aiAdded: true },
  { id: 'e12', date: offsetDay(5), startTime: '18:00', endTime: '19:30', title: 'Командная игра', type: 'TRAINING', intensity: 3 },
  { id: 'e13', date: offsetDay(7), startTime: '10:00', endTime: '11:30', title: 'Силовая (нижний день)', type: 'GYM', intensity: 4 },
  { id: 'e14', date: offsetDay(9), startTime: '17:00', endTime: '20:00', title: 'Almaty Open · 1/8', type: 'MATCH', intensity: 5 },
  { id: 'e15', date: offsetDay(12), startTime: '08:30', endTime: '09:30', title: 'Йога + растяжка', type: 'RECOVERY' },
  { id: 'e16', date: offsetDay(14), startTime: '11:00', endTime: '13:00', title: 'Контрольная сессия', type: 'TRAINING', intensity: 4 },
  { id: 'e17', date: offsetDay(18), startTime: '15:00', endTime: '17:00', title: 'Подготовка к этапу', type: 'TRAINING', intensity: 3 },
  { id: 'e18', date: offsetDay(21), startTime: '09:00', endTime: '12:00', title: 'BWF Regional · группа', type: 'MATCH', intensity: 5 },
]
