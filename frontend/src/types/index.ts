export type AgentStatus = 'ACTIVE' | 'IDLE' | 'PROCESSING'

export type ChatRole = 'user' | 'ai'

export type RiskLevel = 'HIGH' | 'MED' | 'LOW'

export type ChatMessage = {
  id: string
  role: ChatRole
  agentLabel: string
  timestamp: string
  content?: string
  /** Голосовая транскрипция — показывается в чате до нажатия «Отправить» */
  draft?: boolean
  processing?: boolean
  analysis?: {
    level: RiskLevel
    text: string
    pattern: string
  }
}

export type ScheduleItemType = 'TRAINING' | 'RECOVERY' | 'STUDY' | 'MATCH'

export type ScheduleItem = {
  id: string
  day: string
  time: string
  name: string
  type: ScheduleItemType
  intensity?: number
  aiAdded?: boolean
}
