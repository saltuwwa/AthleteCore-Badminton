"""Video LTM pattern detection (no DB / YOLO)."""

from app.memory.video_patterns import (
    build_athlete_baseline,
    detect_improvements,
    detect_repeated_issues,
    findings_to_semantic_candidates,
)


def _episode(
    *,
    issues: list[str],
    drop: float | None = None,
    fatigue: int | None = None,
    attack: float = 0.4,
    speeds: list[float] | None = None,
    ts: str = "2026-01-01",
) -> dict:
    by_min = (
        [{"minute": i, "relative_speed": s} for i, s in enumerate(speeds)]
        if speeds
        else []
    )
    return {
        "timestamp": ts,
        "detected_issues": issues,
        "speed_drop_percent": drop,
        "possible_fatigue_minute": fatigue,
        "attack_defense_ratio": {"attack_like_ratio": attack, "defense_like_ratio": 1 - attack},
        "speed_by_minute": by_min,
        "movement_metrics": {"relative_movement_speed_avg": 0.05},
        "recovery_issues": [],
    }


def test_repeated_issue_three_videos():
    eps = [
        _episode(issues=["possible_late_video_speed_drop"], drop=18, ts="2026-01-01"),
        _episode(issues=["possible_late_video_speed_drop"], drop=20, ts="2026-01-02"),
        _episode(issues=["possible_late_video_speed_drop"], drop=15, ts="2026-01-03"),
    ]
    found = detect_repeated_issues(eps)
    assert any(f.get("issue") == "possible_late_video_speed_drop" for f in found)


def test_improvement_speed_drop_decreasing():
    eps = [
        _episode(issues=[], drop=25, ts="2026-01-01"),
        _episode(issues=[], drop=22, ts="2026-01-02"),
        _episode(issues=[], drop=18, ts="2026-01-03"),
        _episode(issues=[], drop=8, ts="2026-01-04"),
    ]
    found = detect_improvements(eps)
    assert any(f.get("kind") == "improving_speed_drop" for f in found)


def test_baseline_and_semantic_candidates():
    eps = [
        _episode(issues=["possible_low_attack_ratio"], drop=10, fatigue=2, ts="2026-01-01"),
        _episode(issues=["possible_low_attack_ratio"], drop=12, fatigue=2, ts="2026-01-02"),
    ]
    baseline = build_athlete_baseline(eps)
    assert baseline is not None
    repeated = detect_repeated_issues(eps * 2)
    semantic = findings_to_semantic_candidates(repeated, [], baseline)
    keys = {c["key"] for c in semantic}
    assert "performance.video.athlete_baseline" in keys
