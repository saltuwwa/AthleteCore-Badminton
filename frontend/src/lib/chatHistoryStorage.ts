import type { ChatMessage } from '../types'

export const CHAT_HISTORY_KEY = 'athletecore.chat.history'
const STORAGE_VERSION = 1

type StoredPayload = {
  version: number
  messages: ChatMessage[]
}

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v)

const sanitizeAnalysis = (
  raw: unknown,
): ChatMessage['analysis'] | undefined => {
  if (!isRecord(raw)) return undefined
  const level = raw.level
  if (level !== 'HIGH' && level !== 'MED' && level !== 'LOW') return undefined
  const text = typeof raw.text === 'string' ? raw.text : ''
  const pattern = typeof raw.pattern === 'string' ? raw.pattern : ''
  if (!text && !pattern) return undefined
  return { level, text, pattern }
}

const sanitizeStructured = (
  raw: unknown,
): ChatMessage['structured'] | undefined => {
  if (!isRecord(raw)) return undefined
  const out: NonNullable<ChatMessage['structured']> = {}
  const str = (k: keyof NonNullable<ChatMessage['structured']>) => {
    const v = raw[k]
    return typeof v === 'string' ? v : undefined
  }
  const arr = (k: 'improved' | 'repeated') => {
    const v = raw[k]
    if (!Array.isArray(v)) return undefined
    const items = v.filter((x): x is string => typeof x === 'string')
    return items.length ? items : undefined
  }
  out.comparison_label = str('comparison_label')
  out.summary = str('summary')
  out.improved = arr('improved')
  out.repeated = arr('repeated')
  out.recurrence_risk = str('recurrence_risk')
  out.next_training = str('next_training')
  out.pattern_note = str('pattern_note')
  if (Array.isArray(raw.errors)) {
    out.errors = raw.errors
      .filter(isRecord)
      .map((e) => ({
        tag: typeof e.tag === 'string' ? e.tag : undefined,
        category: typeof e.category === 'string' ? e.category : undefined,
        description: typeof e.description === 'string' ? e.description : undefined,
        fix: typeof e.fix === 'string' ? e.fix : undefined,
      }))
  }
  if (
    !out.summary &&
    !out.comparison_label &&
    !out.improved?.length &&
    !out.repeated?.length &&
    !out.errors?.length
  ) {
    return undefined
  }
  return out
}

const sanitizeChatActions = (
  raw: unknown,
): ChatMessage['chatActions'] | undefined => {
  if (!Array.isArray(raw)) return undefined
  const actions = raw
    .filter(isRecord)
    .map((a) => {
      if (typeof a.id !== 'string' || typeof a.label !== 'string') return null
      return {
        id: a.id,
        label: a.label,
        href: typeof a.href === 'string' ? a.href : undefined,
        prefill: typeof a.prefill === 'string' ? a.prefill : undefined,
      }
    })
    .filter((a): a is NonNullable<typeof a> => a !== null)
  return actions.length ? actions : undefined
}

export const sanitizeChatMessage = (raw: unknown): ChatMessage | null => {
  if (!isRecord(raw)) return null
  if (typeof raw.id !== 'string' || !raw.id) return null
  if (raw.role !== 'user' && raw.role !== 'ai') return null
  if (typeof raw.agentLabel !== 'string') return null
  if (typeof raw.timestamp !== 'string') return null
  if (raw.processing === true) return null

  const msg: ChatMessage = {
    id: raw.id,
    role: raw.role,
    agentLabel: raw.agentLabel,
    timestamp: raw.timestamp,
  }
  if (typeof raw.content === 'string') msg.content = raw.content
  if (raw.draft === true) msg.draft = true
  const analysis = sanitizeAnalysis(raw.analysis)
  if (analysis) msg.analysis = analysis
  const structured = sanitizeStructured(raw.structured)
  if (structured) msg.structured = structured
  const chatActions = sanitizeChatActions(raw.chatActions)
  if (chatActions) msg.chatActions = chatActions
  if (raw.comparisonStatus === 'found' || raw.comparisonStatus === 'not_found') {
    msg.comparisonStatus = raw.comparisonStatus
  }
  return msg
}

export const messagesForPersistence = (messages: ChatMessage[]): ChatMessage[] =>
  messages.filter((m) => !m.processing)

export const loadChatHistory = (): ChatMessage[] | null => {
  try {
    const raw = localStorage.getItem(CHAT_HISTORY_KEY)
    if (!raw) return null
    const parsed: unknown = JSON.parse(raw)
    let list: unknown[] | null = null
    if (Array.isArray(parsed)) {
      list = parsed
    } else if (isRecord(parsed) && Array.isArray(parsed.messages)) {
      list = parsed.messages
    }
    if (!list) return null
    const messages = list
      .map(sanitizeChatMessage)
      .filter((m): m is ChatMessage => m !== null)
    if (!messages.length) return null
    const withoutWelcome = messages.filter((m) => m.id !== 'welcome')
    return withoutWelcome.length > 0 ? withoutWelcome : messages
  } catch {
    return null
  }
}

export const saveChatHistory = (messages: ChatMessage[]): void => {
  try {
    const visible = messagesForPersistence(messages)
    const payload: StoredPayload = { version: STORAGE_VERSION, messages: visible }
    localStorage.setItem(CHAT_HISTORY_KEY, JSON.stringify(payload))
  } catch {
    // Quota or private mode — ignore
  }
}

export const clearChatHistory = (): void => {
  try {
    localStorage.removeItem(CHAT_HISTORY_KEY)
  } catch {
    // ignore
  }
}
