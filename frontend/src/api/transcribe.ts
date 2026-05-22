import { apiClient } from './client'

export type TranscribeResponse = {
  text: string
  duration_sec?: number | null
  language?: string
}

export const transcribeAudio = async (audioBlob: Blob) => {
  const formData = new FormData()
  const ext = audioBlob.type.includes('ogg') ? 'ogg' : 'webm'
  formData.append('audio', audioBlob, `recording.${ext}`)
  // Do not set Content-Type manually — axios must add the multipart boundary.
  const { data } = await apiClient.post<TranscribeResponse>('/api/transcribe', formData, {
    timeout: 120_000,
  })
  return data
}
