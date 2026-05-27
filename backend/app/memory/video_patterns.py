from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Any

MIN_EPISODES_FOR_REPEAT = 3
DERIVED_CONFIDENCE_MIN = 0.72


def _sorted_episodes(episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(episodes, key=lambda e: e.get("timestamp") or "")


def _speed_drop(ep: dict[str, Any]) -> float | None:
    v = ep.get("speed_drop_percent")
    return float(v) if v is not None else None


def _fatigue_minute(ep: dict[str, Any]) -> int | None:
    v = ep.get("possible_fatigue_minute")
    return int(v) if v is not None else None


def _attack_ratio(ep: dict[str, Any]) -> float | None:
    ar = ep.get("attack_defense_ratio") or {}
    v = ar.get("attack_like_ratio")
    return float(v) if v is not None else None


def _late_attack_proxy(ep: dict[str, Any]) -> bool:
    """Last minute slower than first — proxy for fading attack pressure."""
    speeds = ep.get("speed_by_minute") or []
    if len(speeds) < 2:
        return False
    first = speeds[0]
    last = speeds[-1]
    s0 = float(first.get("relative_speed", 0) if isinstance(first, dict) else first.relative_speed)
    s1 = float(last.get("relative_speed", 0) if isinstance(last, dict) else last.relative_speed)
    atk = _attack_ratio(ep)
    return s0 > 0 and s1 < s0 * 0.75 and (atk is None or atk < 0.45)


def detect_repeated_issues(episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(episodes) < MIN_EPISODES_FOR_REPEAT:
        return []

    findings: list[dict[str, Any]] = []
    issue_lists = [set(ep.get("detected_issues") or []) for ep in episodes]
    all_tags: Counter[str] = Counter()
    for s in issue_lists:
        all_tags.update(s)

    for tag, count in all_tags.items():
        if count >= MIN_EPISODES_FOR_REPEAT:
            findings.append(
                {
                    "kind": "repeated_issue",
                    "issue": tag,
                    "video_count": count,
                    "confidence": min(0.95, 0.72 + 0.06 * count),
                    "description": (
                        f"Likely recurring pattern (visible in {count} recent video analyses): {tag}"
                    ),
                }
            )

    drops = [e for e in episodes if _speed_drop(e) is not None and float(_speed_drop(e)) >= 12]
    if len(drops) >= MIN_EPISODES_FOR_REPEAT:
        findings.append(
            {
                "kind": "repeated_speed_drop",
                "confidence": 0.78,
                "description": (
                    "Possible repeated late-video speed drop across "
                    f"{len(drops)} analyses (estimated from pose landmarks)."
                ),
            }
        )

    fatigue_mins = [_fatigue_minute(e) for e in episodes if _fatigue_minute(e) is not None]
    if len(fatigue_mins) >= MIN_EPISODES_FOR_REPEAT:
        med = int(mean(fatigue_mins))
        within = sum(1 for m in fatigue_mins if abs(m - med) <= 1)
        if within >= MIN_EPISODES_FOR_REPEAT:
            findings.append(
                {
                    "kind": "repeated_fatigue_minute",
                    "minute_cluster": med,
                    "confidence": 0.76,
                    "description": (
                        f"Possible fatigue-like phase often around minute {med} "
                        "(estimated from visible movement)."
                    ),
                }
            )

    late_atk = sum(1 for e in episodes if _late_attack_proxy(e))
    if late_atk >= MIN_EPISODES_FOR_REPEAT:
        findings.append(
            {
                "kind": "repeated_late_attack_decline",
                "confidence": 0.74,
                "description": (
                    "Attack-like movement may decrease in later minutes across multiple videos."
                ),
            }
        )

    recovery_tags: Counter[str] = Counter()
    for ep in episodes:
        for r in ep.get("recovery_issues") or []:
            recovery_tags[str(r)[:120]] += 1
    for tag, count in recovery_tags.items():
        if count >= MIN_EPISODES_FOR_REPEAT and tag:
            findings.append(
                {
                    "kind": "repeated_recovery_issue",
                    "issue": tag,
                    "confidence": 0.73,
                    "description": f"Possible recurring recovery/load signal: {tag}",
                }
            )

    return findings


def detect_improvements(episodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = _sorted_episodes(episodes)
    if len(ordered) < 3:
        return []

    findings: list[dict[str, Any]] = []
    n = len(ordered)
    early = ordered[: max(1, n // 2)]
    late = ordered[n // 2 :]

    early_drops = [_speed_drop(e) for e in early if _speed_drop(e) is not None]
    late_drops = [_speed_drop(e) for e in late if _speed_drop(e) is not None]
    if early_drops and late_drops:
        if mean(late_drops) < mean(early_drops) - 5.0:
            findings.append(
                {
                    "kind": "improving_speed_drop",
                    "confidence": 0.75,
                    "description": (
                        "Speed drop percent may be decreasing over recent videos "
                        "(estimated from pose landmarks)."
                    ),
                }
            )

    early_fat = [_fatigue_minute(e) for e in early if _fatigue_minute(e) is not None]
    late_fat = [_fatigue_minute(e) for e in late if _fatigue_minute(e) is not None]
    if early_fat and late_fat and mean(late_fat) > mean(early_fat) + 0.5:
        findings.append(
            {
                "kind": "later_fatigue_minute",
                "confidence": 0.74,
                "description": (
                    "Possible fatigue-like minute appears later in recent videos — "
                    "may indicate better pacing."
                ),
            }
        )

    late_atk_stable = [_attack_ratio(e) for e in late if _attack_ratio(e) is not None]
    if len(late_atk_stable) >= 3:
        var = max(late_atk_stable) - min(late_atk_stable)
        if var < 0.12 and mean(late_atk_stable) >= 0.38:
            findings.append(
                {
                    "kind": "stable_attack_ratio",
                    "confidence": 0.73,
                    "description": (
                        "Attack-like ratio appears more stable in recent analyses."
                    ),
                }
            )

    return findings


def build_athlete_baseline(episodes: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not episodes:
        return None
    recent = _sorted_episodes(episodes)[-10:]
    speeds = []
    drops = []
    fatigues = []
    attacks = []
    for ep in recent:
        mm = ep.get("movement_metrics") or {}
        if mm.get("relative_movement_speed_avg") is not None:
            speeds.append(float(mm["relative_movement_speed_avg"]))
        d = _speed_drop(ep)
        if d is not None:
            drops.append(float(d))
        f = _fatigue_minute(ep)
        if f is not None:
            fatigues.append(float(f))
        a = _attack_ratio(ep)
        if a is not None:
            attacks.append(float(a))

    return {
        "sample_count": len(recent),
        "avg_relative_speed": round(mean(speeds), 4) if speeds else None,
        "avg_speed_drop_percent": round(mean(drops), 2) if drops else None,
        "typical_fatigue_minute": round(mean(fatigues), 1) if fatigues else None,
        "avg_attack_like_ratio": round(mean(attacks), 3) if attacks else None,
        "disclaimer": "Baseline estimated from recent pose-based video analyses only.",
    }


def findings_to_semantic_candidates(
    repeated: list[dict[str, Any]],
    improvements: list[dict[str, Any]],
    baseline: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    for item in repeated:
        conf = float(item.get("confidence", 0))
        if conf < DERIVED_CONFIDENCE_MIN:
            continue
        candidates.append(
            {
                "type": "fact",
                "key": "performance.video.repeated_error_pattern",
                "value": str(item.get("description", ""))[:500],
                "confidence": conf,
                "supersedes_same_key": True,
                "memory_layer": "semantic",
                "event_type": None,
                "importance": 0.82,
                "is_repeated_pattern": True,
                "payload": item,
            }
        )

    for item in improvements:
        conf = float(item.get("confidence", 0))
        if conf < DERIVED_CONFIDENCE_MIN:
            continue
        candidates.append(
            {
                "type": "fact",
                "key": "performance.video.improvement_pattern",
                "value": str(item.get("description", ""))[:500],
                "confidence": conf,
                "supersedes_same_key": True,
                "memory_layer": "semantic",
                "event_type": None,
                "importance": 0.78,
                "is_repeated_pattern": False,
                "payload": item,
            }
        )

    if baseline and baseline.get("sample_count", 0) >= 2:
        candidates.append(
            {
                "type": "fact",
                "key": "performance.video.athlete_baseline",
                "value": (
                    "Pose-video baseline (approximate): "
                    f"avg speed {baseline.get('avg_relative_speed')}, "
                    f"avg drop {baseline.get('avg_speed_drop_percent')}%, "
                    f"typical fatigue minute {baseline.get('typical_fatigue_minute')}."
                )[:500],
                "confidence": 0.8,
                "supersedes_same_key": True,
                "memory_layer": "semantic",
                "event_type": None,
                "importance": 0.75,
                "payload": baseline,
            }
        )

    return candidates
