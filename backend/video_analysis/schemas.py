from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class VideoUploadResponse(BaseModel):
    video_id: str
    filename: str
    duration_sec: float | None = None
    fps: float | None = None
    frame_count: int | None = None
    width: int | None = None
    height: int | None = None


class PlayerBBox(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float


class DetectedPlayer(BaseModel):
    track_id: int
    label: str
    bbox: PlayerBBox
    confidence: float
    frame_index: int
    sample_count: int


class DetectPlayersRequest(BaseModel):
    video_id: str
    match_type: Literal["singles", "doubles", "mixed"] = "singles"
    max_players: int | None = Field(default=None, ge=2, le=8)


class DetectPlayersResponse(BaseModel):
    video_id: str
    preview_frame_base64: str
    preview_frame_index: int
    players: list[DetectedPlayer]
    tracking_available: bool = False


class AnalyzeVideoRequest(BaseModel):
    video_id: str
    user_id: str = "aigerim"
    match_type: Literal["singles", "doubles", "mixed"]
    target_track_ids: list[int] = Field(..., min_length=1, max_length=4)
    debug: bool = False
    target_label: str | None = None
    target_jersey_color: str | None = None
    target_court_side: Literal["near", "far", "unknown"] | None = None


class SpeedByMinute(BaseModel):
    minute: int
    relative_speed: float
    frame_samples: int


class KeyMoment(BaseModel):
    timestamp_sec: float
    label: str
    note: str


class PlayerMovementMetrics(BaseModel):
    track_id: int
    relative_movement_speed_avg: float
    speed_by_minute: list[SpeedByMinute]
    speed_drop_percent: float | None = None
    slowest_minute: int | None = None
    attack_like_ratio: float
    defense_like_ratio: float
    possible_fatigue_minute: int | None = None
    key_moments: list[KeyMoment]


class DoublesTeamMetrics(BaseModel):
    partner_distance_by_minute: list[dict[str, Any]]
    overlap_moments: list[KeyMoment]
    gap_moments: list[KeyMoment]
    players: list[PlayerMovementMetrics]


class TimeRangeLabel(BaseModel):
    start: str
    end: str


class IgnoredSegment(TimeRangeLabel):
    reason: str


class SegmentFilterSummary(BaseModel):
    valid_segments: list[TimeRangeLabel] = Field(default_factory=list)
    ignored_segments: list[IgnoredSegment] = Field(default_factory=list)
    valid_gameplay_ratio: float = 0.0
    analysis_confidence: float = 0.0
    warning: str | None = None


class VideoMetricsSummary(BaseModel):
    video_id: str
    match_type: Literal["singles", "doubles", "mixed"]
    target_track_ids: list[int]
    duration_sec: float
    fps: float
    disclaimer: str
    singles: PlayerMovementMetrics | None = None
    doubles: DoublesTeamMetrics | None = None
    segment_filter: SegmentFilterSummary | None = None
    raw_notes: dict[str, Any] = Field(default_factory=dict)


class CoachingFeedback(BaseModel):
    short_summary: str
    key_timeline_moments: list[str]
    speed_trend: str
    attack_vs_defense_analysis: str
    possible_fatigue_moment: str | None = None
    coaching_recommendations: list[str] = Field(..., min_length=1, max_length=8)
    drill_for_next_training: str
    repeated_mistakes: list[str] = Field(default_factory=list)
    improvements_noted: list[str] = Field(default_factory=list)
    regressions_noted: list[str] = Field(default_factory=list)
    next_training_focus: str | None = None
    methodology_sources_used: list[str] = Field(default_factory=list)
    disclaimer: str


class VideoMemorySummary(BaseModel):
    past_video_count: int = 0
    repeated_patterns: list[str] = Field(default_factory=list)
    improvement_patterns: list[str] = Field(default_factory=list)
    athlete_baseline: dict | None = None


class VideoDebugSummary(BaseModel):
    valid_gameplay_ratio: float = 0.0
    players_found: int = 0
    tracking_stability: float = 0.0
    gemini_sec: float | None = None
    total_sec: float | None = None


class AnalyzeVideoResponse(BaseModel):
    video_id: str
    metrics: VideoMetricsSummary
    coaching_feedback: CoachingFeedback
    memory_summary: VideoMemorySummary | None = None
    debug_report_id: str | None = None
    debug_available: bool = False
    debug_summary: VideoDebugSummary | None = None
