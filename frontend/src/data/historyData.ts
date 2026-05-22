export type HistoryItemType = 'MATCH' | 'TRAINING' | 'VOICE' | 'NOTE'

export type HistoryItem = {
  id: string
  type: HistoryItemType
  date: string
  title: string
  summary: string
  tags?: string[]
}

export const historyItems: HistoryItem[] = [
  {
    id: 'h1',
    type: 'MATCH',
    date: '21 апр, 19:40',
    title: 'Матч против А. Жакаевой',
    summary: 'Победа 2-1. Аналитик отметил повторяющуюся ошибку в защите по корту слева. Score 8.2.',
    tags: ['Almaty Cup', 'WS', 'Рекуррентная ошибка'],
  },
  {
    id: 'h2',
    type: 'VOICE',
    date: '21 апр, 21:05',
    title: 'Голосовой лог после матча · 02:14',
    summary: 'Транскрипт: усталость в третьем сете, не успевала на укороченные. Агент создал задачу на спарринг-игру коротких ударов.',
    tags: ['voice-log', 'fatigue'],
  },
  {
    id: 'h3',
    type: 'TRAINING',
    date: '20 апр, 11:30',
    title: 'Скоростная работа · 90 мин',
    summary: 'Интенсивность 4/5. Реакция в норме. Health Coach снизил нагрузку на следующий день.',
    tags: ['speed', 'rpe-7'],
  },
  {
    id: 'h4',
    type: 'NOTE',
    date: '20 апр, 09:10',
    title: 'Заметка тренера',
    summary: 'Работаем над переводом темпа в розыгрышах длиннее 12 ударов.',
    tags: ['тактика'],
  },
  {
    id: 'h5',
    type: 'MATCH',
    date: '15 апр, 18:20',
    title: 'KZ Open · 1/8',
    summary: 'Поражение 0-2 от Я. Сидоровой. Слабая работа на сетке во втором сете. Score 6.9.',
    tags: ['KZ Open', 'Loss'],
  },
  {
    id: 'h6',
    type: 'TRAINING',
    date: '14 апр, 09:00',
    title: 'Технический блок · сетка',
    summary: 'Подача справа после длинных розыгрышей. 3/5 интенсивность.',
    tags: ['technique'],
  },
  {
    id: 'h7',
    type: 'VOICE',
    date: '13 апр, 22:00',
    title: 'Голосовой лог · 01:48',
    summary: 'Самочувствие 8/10. План на завтра подтверждён.',
    tags: ['voice-log'],
  },
]
