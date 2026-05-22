import { apiClient } from './client'

export type ChatApiResponse = {
  message: string
  thread_id: string
  agents_used: string[]
  requires_confirmation: boolean
  analysis: {
    errors?: Array<{
      tag?: string
      category?: string
      description?: string
      fix?: string
    }>
    pattern_note?: string
  } | null
  needs_memory: boolean
  memory_citations_count: number
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
