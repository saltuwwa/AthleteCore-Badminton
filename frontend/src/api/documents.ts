import { apiClient } from './client'

export type DocumentAction = 'parse_results' | 'find_my_matches' | 'compare_past'
export type DetectedDocType = 'pdf' | 'docx' | 'xlsx' | 'csv' | 'image' | 'unknown'

export type DocumentUploadResponse = {
  document_id: string
  filename: string
  detected_type: DetectedDocType
  size_bytes: number
}

export type DocumentAnalyzeResponse = {
  document_id: string
  action: DocumentAction
  assistant_message: string
  structured: {
    security_notice?: string | null
    tournament_name?: string | null
  }
  memory_saved: boolean
}

const TYPE_LABEL: Record<DetectedDocType, string> = {
  pdf: 'PDF',
  docx: 'Word',
  xlsx: 'Excel',
  csv: 'CSV',
  image: 'Изображение',
  unknown: 'Файл',
}

export function documentTypeLabel(t: DetectedDocType): string {
  return TYPE_LABEL[t] ?? 'Файл'
}

export async function uploadDocument(file: File): Promise<DocumentUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await apiClient.post<DocumentUploadResponse>('/api/documents/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function analyzeDocument(body: {
  document_id: string
  action: DocumentAction
  user_id?: string
  athlete_name?: string
}): Promise<DocumentAnalyzeResponse> {
  const { data } = await apiClient.post<DocumentAnalyzeResponse>('/api/documents/analyze', {
    user_id: body.user_id ?? 'aigerim',
    ...body,
  })
  return data
}
