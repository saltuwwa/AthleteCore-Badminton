from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from video_analysis.schemas import CoachingFeedback, VideoMetricsSummary

MatchType = Literal["singles", "doubles", "mixed"]


def _primary_player_metrics(metrics: VideoMetricsSummary) -> dict[str, Any]:
    if metrics.singles:
        return metrics.singles.model_dump(mode="json")
    if metrics.doubles and metrics.doubles.players:
        return metrics.doubles.players[0].model_dump(mode="json")
    return {}


def extract_detected_issues(metrics: VideoMetricsSummary) -> list[str]:
    """Heuristic issue tags from pose metrics (approximate, for pattern matching)."""
    issues: list[str] = []
    pm = _primary_player_metrics(metrics)
    if not pm:
        return issues

    drop = pm.get("speed_drop_percent")
    if drop is not None and float(drop) >= 12.0:
        issues.append("possible_late_video_speed_drop")

    fatigue = pm.get("possible_fatigue_minute")
    if fatigue is not None:
        issues.append(f"possible_fatigue_minute_{int(fatigue)}")

    atk = float(pm.get("attack_like_ratio") or 0.5)
    def_ = float(pm.get("defense_like_ratio") or 0.5)
    if atk < 0.35 and def_ > 0.55:
        issues.append("possible_low_attack_ratio")

    by_min = pm.get("speed_by_minute") or []
    if len(by_min) >= 2:
        first = float(by_min[0].get("relative_speed", 0) if isinstance(by_min[0], dict) else by_min[0].relative_speed)
        last = float(by_min[-1].get("relative_speed", 0) if isinstance(by_min[-1], dict) else by_min[-1].relative_speed)
        if first > 0 and last < first * 0.7:
            issues.append("possible_speed_decline_across_minutes")

    for km in pm.get("key_moments") or []:
        label = km.get("label") if isinstance(km, dict) else getattr(km, "label", "")
        if label == "possible_slow_phase":
            issues.append("possible_recovery_slow_phase")

    if metrics.doubles:
        if len(metrics.doubles.overlap_moments) >= 3:
            issues.append("possible_doubles_partner_overlap")
        if len(metrics.doubles.gap_moments) >= 3:
            issues.append("possible_doubles_partner_gap")

    return sorted(set(issues))


def extract_recovery_issues(metrics: VideoMetricsSummary) -> list[str]:
    issues: list[str] = []
    pm = _primary_player_metrics(metrics)
    for km in pm.get("key_moments") or []:
        note = (km.get("note") if isinstance(km, dict) else getattr(km, "note", "")) or ""
        label = km.get("label") if isinstance(km, dict) else getattr(km, "label", "")
        if "slow" in label or "recovery" in note.lower() or "slow" in note.lower():
            issues.append(note[:200] if note else label)
    drop = pm.get("speed_drop_percent")
    if drop is not None and float(drop) >= 15:
        issues.append(
            "Possible recovery/load issue: estimated speed drop based on visible movement."
        )
    return issues[:6]


def build_video_analysis_payload(
    *,
    user_id: str,
    metrics: VideoMetricsSummary,
    coaching: CoachingFeedback | None = None,
    event_id: str | None = None,
    match_type: MatchType | None = None,
) -> dict[str, Any]:
    """Structured episodic payload — never raw video."""
    pm = _primary_player_metrics(metrics)
    eid = event_id or metrics.video_id or str(uuid.uuid4())
    mt: MatchType = match_type or metrics.match_type  # type: ignore[assignment]
    if mt not in ("singles", "doubles", "mixed"):
        mt = metrics.match_type  # type: ignore[assignment]

    speed_by_minute = pm.get("speed_by_minute") or []
    recommendations = list(coaching.coaching_recommendations) if coaching else []

    return {
        "user_id": user_id,
        "event_id": eid,
        "timestamp": datetime.now(UTC).isoformat(),
        "match_type": mt,
        "target_track_ids": metrics.target_track_ids,
        "video_duration_sec": metrics.duration_sec,
        "movement_metrics": {
            "relative_movement_speed_avg": pm.get("relative_movement_speed_avg"),
            "track_id": pm.get("track_id"),
            "doubles_team": metrics.doubles.model_dump(mode="json") if metrics.doubles else None,
        },
        "speed_by_minute": speed_by_minute,
        "speed_drop_percent": pm.get("speed_drop_percent"),
        "attack_defense_ratio": {
            "attack_like_ratio": pm.get("attack_like_ratio"),
            "defense_like_ratio": pm.get("defense_like_ratio"),
        },
        "possible_fatigue_minute": pm.get("possible_fatigue_minute"),
        "recovery_issues": extract_recovery_issues(metrics),
        "key_moments_timeline": pm.get("key_moments") or [],
        "detected_issues": extract_detected_issues(metrics),
        "recommendations": recommendations,
        "importance": _importance_score(metrics, coaching),
        "source_video_id": metrics.video_id,
    }


def _importance_score(
    metrics: VideoMetricsSummary,
    coaching: CoachingFeedback | None,
) -> float:
    score = 0.55
    pm = _primary_player_metrics(metrics)
    if pm.get("speed_drop_percent") and float(pm["speed_drop_percent"]) >= 15:
        score += 0.15
    if pm.get("possible_fatigue_minute") is not None:
        score += 0.1
    if len(extract_detected_issues(metrics)) >= 2:
        score += 0.1
    if coaching and len(coaching.coaching_recommendations) >= 3:
        score += 0.05
    return min(score, 0.95)


def payload_to_episode_row(payload: dict[str, Any]) -> dict[str, Any]:
    """Candidate dict for apply_supersession_and_insert."""
    vid = payload["source_video_id"]
    summary = (
        f"Video analysis ({payload['match_type']}): "
        f"duration {payload['video_duration_sec']:.0f}s, "
        f"issues={', '.join(payload.get('detected_issues') or []) or 'none'}"
    )
    return {
        "type": "event",
        "key": f"video.analysis.{vid}",
        "value": summary,
        "confidence": 0.92,
        "supersedes_same_key": True,
        "memory_layer": "episodic",
        "event_type": "video_analysis",
        "importance": float(payload.get("importance", 0.6)),
        "is_repeated_pattern": False,
        "is_user_confirmed": False,
        "payload": payload,
    }


def episode_from_memory_row(memory) -> dict[str, Any]:
    p = dict(memory.payload or {})
    p.setdefault("event_id", p.get("source_video_id", str(memory.id)))
    p.setdefault("timestamp", memory.created_at.isoformat() if memory.created_at else "")
    return p
