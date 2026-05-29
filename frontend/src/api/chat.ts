import { apiClient } from './client'

export type ChatAnalysisPayload = {
  comparison_label?: string
  summary?: string
  improved?: string[]
  repeated?: string[]
  recurrence_risk?: string
  next_training?: string
  errors?: Array<{
    tag?: string
    category?: string
    description?: string
    fix?: string
  }>
  pattern_note?: string
}

export type LatencyTrace = {
  request_id: string
  total_ms: number
  stages: Record<string, number>
  llm_calls: Array<{
    name: string
    model: string
    duration_ms: number
    prompt_chars: number
    completion_chars: number
  }>
  db_calls: Array<{
    name: string
    duration_ms: number
    rows: number
  }>
}

export type ChatApiResponse = {
  message: string
  thread_id: string
  agents_used: string[]
  requires_confirmation: boolean
  analysis: ChatAnalysisPayload | null
  needs_memory: boolean
  memory_citations_count: number
  comparison_status?: 'found' | 'not_found' | null
  comparison_label?: string | null
  chat_actions?: Array<{
    id: string
    label: string
    href?: string | null
    prefill?: string | null
  }>
  latency_trace?: LatencyTrace | null
}

export const fetchChatSuggestions = async (userId = 'aigerim', sessionId = 'main') => {
  const { data } = await apiClient.get<{ suggestions: string[] }>('/api/chat/suggestions', {
    params: { user_id: userId, session_id: sessionId },
  })
  return data.suggestions
}

export const sendMessage = async (
  message: string,
  options?: { threadId?: string; userId?: string; sessionId?: string },
  imageFile?: File,
) => {
  const formData = new FormData()
  formData.append('message', message)
  formData.append('user_id', options?.userId ?? 'aigerim')
  formData.append('session_id', options?.sessionId ?? 'main')
  if (options?.threadId) formData.append('thread_id', options.threadId)
  if (imageFile) formData.append('image', imageFile)
  const { data } = await apiClient.post<ChatApiResponse>('/api/chat', formData)
  return data
}
