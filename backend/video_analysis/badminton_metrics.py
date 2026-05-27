from __future__ import annotations

from statistics import mean, median
from typing import Any

from video_analysis.feature_extraction import MotionSample, extract_motion_series, partner_distance_series
from video_analysis.player_tracking import frame_tracks_from_payload
from video_analysis.schemas import (
    DoublesTeamMetrics,
    KeyMoment,
    PlayerMovementMetrics,
    SpeedByMinute,
    VideoMetricsSummary,
)

DISCLAIMER = (
    "Metrics are estimated from visible pose landmarks and court movement only. "
    "They are approximate — not exact biomechanics, not shuttle speed, not official match statistics."
)


def _minute_bucket(ts: float) -> int:
    return max(0, int(ts // 60))


def _speed_by_minute(samples: list[MotionSample]) -> list[SpeedByMinute]:
    buckets: dict[int, list[float]] = {}
    for s in samples:
        if s.relative_speed <= 0:
            continue
        m = _minute_bucket(s.timestamp_sec)
        buckets.setdefault(m, []).append(s.relative_speed)
    return [
        SpeedByMinute(
            minute=m,
            relative_speed=round(mean(vals), 4),
            frame_samples=len(vals),
        )
        for m, vals in sorted(buckets.items())
    ]


def _attack_defense_ratios(samples: list[MotionSample]) -> tuple[float, float]:
    if not samples:
        return 0.5, 0.5
    attack_score = 0
    defense_score = 0
    speeds = [s.relative_speed for s in samples if s.relative_speed > 0]
    if not speeds:
        return 0.5, 0.5
    thr = median(speeds)
    for s in samples:
        burst = s.relative_speed > thr * 1.25 or s.wrist_speed > thr * 0.8
        forward_burst = s.forward_v > 0 and burst
        if forward_burst:
            attack_score += 1
        elif s.relative_speed < thr * 0.85:
            defense_score += 1
        else:
            defense_score += 0.5
    total = attack_score + defense_score
    if total <= 0:
        return 0.5, 0.5
    return round(attack_score / total, 3), round(defense_score / total, 3)


def _speed_drop_and_fatigue(speeds_by_min: list[SpeedByMinute]) -> tuple[float | None, int | None, int | None]:
    if len(speeds_by_min) < 2:
        return None, None, None
    vals = [s.relative_speed for s in speeds_by_min]
    first = mean(vals[: max(1, len(vals) // 2)])
    last = mean(vals[len(vals) // 2 :])
    drop = round((1 - last / first) * 100, 1) if first > 0 else None
    slowest = min(speeds_by_min, key=lambda x: x.relative_speed)
    fatigue_min = slowest.minute if drop and drop > 15 else None
    return drop, slowest.minute, fatigue_min


def _key_moments(samples: list[MotionSample], speeds_by_min: list[SpeedByMinute]) -> list[KeyMoment]:
    moments: list[KeyMoment] = []
    if not samples:
        return moments
    sorted_s = sorted(samples, key=lambda x: x.relative_speed, reverse=True)
    top = sorted_s[:3]
    for s in top:
        if s.relative_speed <= 0:
            continue
        moments.append(
            KeyMoment(
                timestamp_sec=round(s.timestamp_sec, 1),
                label="likely_high_activity",
                note=(
                    "Possible attack-like or high-intensity movement "
                    "(estimated from pose landmarks)."
                ),
            )
        )
    if speeds_by_min:
        slow = min(speeds_by_min, key=lambda x: x.relative_speed)
        moments.append(
            KeyMoment(
                timestamp_sec=float(slow.minute * 60),
                label="possible_slow_phase",
                note=f"Slowest visible minute index {slow.minute} (relative speed).",
            )
        )
    return moments[:8]


def _player_metrics(track_id: int, samples: list[MotionSample]) -> PlayerMovementMetrics:
    speeds = [s.relative_speed for s in samples if s.relative_speed > 0]
    avg = round(mean(speeds), 4) if speeds else 0.0
    by_min = _speed_by_minute(samples)
    drop, slow_min, fatigue_min = _speed_drop_and_fatigue(by_min)
    atk, def_ = _attack_defense_ratios(samples)
    return PlayerMovementMetrics(
        track_id=track_id,
        relative_movement_speed_avg=avg,
        speed_by_minute=by_min,
        speed_drop_percent=drop,
        slowest_minute=slow_min,
        attack_like_ratio=atk,
        defense_like_ratio=def_,
        possible_fatigue_minute=fatigue_min,
        key_moments=_key_moments(samples, by_min),
    )


def _overlap_gap_moments(
    distances: list[dict[str, Any]], *, frame_diagonal: float
) -> tuple[list[KeyMoment], list[KeyMoment]]:
    if not distances:
        return [], []
    vals = [d["relative_distance"] for d in distances]
    med = median(vals)
    overlap_thr = med * 0.55
    gap_thr = med * 1.45
    overlaps: list[KeyMoment] = []
    gaps: list[KeyMoment] = []
    for d in distances:
        ts = float(d["timestamp_sec"])
        dist = float(d["relative_distance"])
        if dist < overlap_thr:
            overlaps.append(
                KeyMoment(
                    timestamp_sec=ts,
                    label="partner_overlap",
                    note="Partners likely close together (estimated spacing).",
                )
            )
        elif dist > gap_thr:
            gaps.append(
                KeyMoment(
                    timestamp_sec=ts,
                    label="partner_gap",
                    note="Partners likely far apart (estimated spacing).",
                )
            )
    return overlaps[:6], gaps[:6]


def build_metrics_summary(
    *,
    video_id: str,
    match_type: str,
    target_track_ids: list[int],
    tracking: dict[str, Any],
    duration_sec: float,
) -> VideoMetricsSummary:
    fps = float(tracking.get("fps") or 25.0)
    w = int(tracking.get("width") or 1280)
    h = int(tracking.get("height") or 720)
    diag = (w * w + h * h) ** 0.5

    tracks = frame_tracks_from_payload(tracking)
    series = extract_motion_series(
        tracks,
        track_ids=set(target_track_ids),
        fps=fps,
        frame_diagonal=diag,
    )

    if match_type == "doubles" and len(target_track_ids) >= 2:
        players = [_player_metrics(tid, series.get(tid, [])) for tid in target_track_ids[:2]]
        dist_series = partner_distance_series(series, target_track_ids[:2], frame_diagonal=diag)
        by_min: dict[int, list[float]] = {}
        for p in dist_series:
            m = _minute_bucket(float(p["timestamp_sec"]))
            by_min.setdefault(m, []).append(float(p["relative_distance"]))
        partner_by_min = [
            {"minute": m, "avg_relative_distance": round(mean(v), 4), "samples": len(v)}
            for m, v in sorted(by_min.items())
        ]
        overlaps, gaps = _overlap_gap_moments(dist_series, frame_diagonal=diag)
        doubles = DoublesTeamMetrics(
            partner_distance_by_minute=partner_by_min,
            overlap_moments=overlaps,
            gap_moments=gaps,
            players=players,
        )
        return VideoMetricsSummary(
            video_id=video_id,
            match_type="doubles",
            target_track_ids=target_track_ids,
            duration_sec=duration_sec,
            fps=fps,
            disclaimer=DISCLAIMER,
            doubles=doubles,
            raw_notes={"frame_diagonal_px": round(diag, 1), "tracking_frames": len(tracks)},
        )

    tid = target_track_ids[0]
    singles = _player_metrics(tid, series.get(tid, []))
    return VideoMetricsSummary(
        video_id=video_id,
        match_type="singles",
        target_track_ids=target_track_ids,
        duration_sec=duration_sec,
        fps=fps,
        disclaimer=DISCLAIMER,
        singles=singles,
        raw_notes={"frame_diagonal_px": round(diag, 1), "tracking_frames": len(tracks)},
    )
