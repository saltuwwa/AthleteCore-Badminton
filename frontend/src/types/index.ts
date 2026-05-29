export type AgentStatus = 'ACTIVE' | 'IDLE' | 'PROCESSING'

export type ChatRole = 'user' | 'ai'

export type RiskLevel = 'HIGH' | 'MED' | 'LOW'

export type ChatAction = {
  id: string
  label: string
  href?: string
  prefill?: string
}

export type AnalystStructured = {
  comparison_label?: string
  summary?: string
  improved?: string[]
  repeated?: string[]
  recurrence_risk?: string
  next_training?: string
  pattern_note?: string
  errors?: Array<{
    tag?: string
    category?: string
    description?: string
    fix?: string
  }>
}

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
  structured?: AnalystStructured
  chatActions?: ChatAction[]
  comparisonStatus?: 'found' | 'not_found'
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
