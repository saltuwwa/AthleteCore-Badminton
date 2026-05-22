import type { ChatApiResponse } from '../api/chat'
import type { ChatMessage, RiskLevel } from '../types'

const AGENT_LABELS: Record<string, string> = {
  analyst: 'ANALYST AGENT',
  health_coach: 'HEALTH COACH',
  scheduler: 'SCHEDULE AGENT',
  direct: 'ATHLETE CORE',
}

export const agentLabel = (agents: string[] | undefined) => {
  const key = agents?.[0]
  if (!key) return 'ATHLETE CORE'
  return AGENT_LABELS[key] ?? key.toUpperCase()
}

const normalizeTag = (tag?: string): RiskLevel => {
  const t = (tag ?? 'MED').toUpperCase()
  if (t === 'HIGH' || t === 'MED' || t === 'LOW') return t
  return 'MED'
}

export const mapAnalysisToMessage = (
  analysis: ChatApiResponse['analysis'],
): ChatMessage['analysis'] | undefined => {
  const first = analysis?.errors?.[0]
  if (!first) return undefined
  return {
    level: normalizeTag(first.tag),
    text: first.description || first.fix || '',
    pattern: first.fix || analysis?.pattern_note || '',
  }
}

export type AnalysisErrorRow = {
  level: RiskLevel
  title: string
  cause: string
  fix: string
  pattern: string
}

export const mapAnalysisToRows = (
  analysis: ChatApiResponse['analysis'],
): AnalysisErrorRow[] => {
  if (!analysis?.errors?.length) return []
  return analysis.errors.map((e) => ({
    level: normalizeTag(e.tag),
    title: e.description || e.category || 'Ошибка',
    cause: e.category || '—',
    fix: e.fix || '—',
    pattern: analysis.pattern_note || '',
  }))
}
