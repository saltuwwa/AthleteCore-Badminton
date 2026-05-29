import { apiClient } from './client'

export type MatchType = 'singles' | 'doubles' | 'mixed'

export type DetectedPlayer = {
  track_id: number
  label: string
  bbox: { x1: number; y1: number; x2: number; y2: number }
  confidence: number
  frame_index: number
  sample_count: number
}

export type VideoUploadResponse = {
  video_id: string
  filename: string
  duration_sec: number | null
}

export type DetectPlayersResponse = {
  video_id: string
  preview_frame_base64: string
  preview_frame_index: number
  players: DetectedPlayer[]
}

export type CoachingFeedback = {
  short_summary: string
  key_timeline_moments: string[]
  speed_trend: string
  attack_vs_defense_analysis: string
  possible_fatigue_moment: string | null
  coaching_recommendations: string[]
  drill_for_next_training: string
  repeated_mistakes: string[]
  improvements_noted: string[]
  regressions_noted: string[]
  next_training_focus: string | null
}

export type VideoMemorySummary = {
  past_video_count: number
  repeated_patterns: string[]
  improvement_patterns: string[]
  athlete_baseline: Record<string, unknown> | null
}

export type SegmentFilterSummary = {
  valid_segments: { start: string; end: string }[]
  ignored_segments: { start: string; end: string; reason: string }[]
  valid_gameplay_ratio: number
  analysis_confidence: number
  warning: string | null
}

export type VideoDebugSummary = {
  valid_gameplay_ratio: number
  players_found: number
  tracking_stability: number
  gemini_sec: number | null
  total_sec: number | null
}

export type VideoDebugBundle = Record<string, unknown>

export type AnalyzeVideoResponse = {
  video_id: string
  debug_report_id?: string | null
  debug_available?: boolean
  debug_summary?: VideoDebugSummary | null
  metrics: {
    duration_sec: number
    segment_filter?: SegmentFilterSummary | null
    singles?: {
      relative_movement_speed_avg: number
      speed_drop_percent: number | null
      attack_like_ratio: number
      defense_like_ratio: number
      possible_fatigue_minute: number | null
    }
    doubles?: {
      players: Array<{
        track_id: number
        relative_movement_speed_avg: number
        attack_like_ratio: number
        possible_fatigue_minute: number | null
      }>
    }
  }
  coaching_feedback: CoachingFeedback
  memory_summary: VideoMemorySummary | null
}

export async function uploadVideo(file: File): Promise<VideoUploadResponse> {
  const form = new FormData()
  form.append('file', file)
  const { data } = await apiClient.post<VideoUploadResponse>('/video/upload', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function detectPlayers(
  videoId: string,
  matchType: MatchType = 'singles',
  maxPlayers?: number,
): Promise<DetectPlayersResponse> {
  const { data } = await apiClient.post<DetectPlayersResponse>('/video/detect-players', {
    video_id: videoId,
    match_type: matchType,
    max_players: maxPlayers ?? (matchType === 'singles' ? 2 : 4),
  })
  return data
}

export async function analyzeVideo(body: {
  video_id: string
  user_id?: string
  match_type: MatchType
  target_track_ids: number[]
  debug?: boolean
  target_label?: string
  target_jersey_color?: string
  target_court_side?: 'near' | 'far' | 'unknown'
}): Promise<AnalyzeVideoResponse> {
  const { data } = await apiClient.post<AnalyzeVideoResponse>(
    '/video/analyze',
    {
      user_id: body.user_id ?? 'aigerim',
      ...body,
    },
    { params: body.debug ? { debug: true } : undefined },
  )
  return data
}

export async function fetchVideoDebug(videoId: string): Promise<VideoDebugBundle> {
  const { data } = await apiClient.get<VideoDebugBundle>(`/video/${videoId}/debug`)
  return data
}
