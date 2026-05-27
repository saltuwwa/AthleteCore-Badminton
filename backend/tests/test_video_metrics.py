"""Unit tests for pose-derived metrics (no YOLO required)."""

from video_analysis.badminton_metrics import build_metrics_summary
def _synthetic_tracking(track_id: int, n: int = 60, fps: float = 25.0) -> dict:
    frames = []
    for i in range(n):
        t = i / fps
        frames.append(
            {
                "frame_index": i,
                "timestamp_sec": round(t, 3),
                "track_id": track_id,
                "bbox": [100.0 + i, 200.0, 150.0 + i, 280.0],
                "confidence": 0.9,
                "keypoints": [[0, 0, 0]] * 17,
            }
        )
    return {"fps": fps, "width": 1280, "height": 720, "frames": frames}


def test_singles_metrics_shape():
    tracking = _synthetic_tracking(1)
    summary = build_metrics_summary(
        video_id="test-vid",
        match_type="singles",
        target_track_ids=[1],
        tracking=tracking,
        duration_sec=60.0,
    )
    assert summary.match_type == "singles"
    assert summary.singles is not None
    assert summary.singles.track_id == 1
    assert "pose landmarks" in summary.disclaimer.lower()


def test_doubles_team_metrics():
    t1 = _synthetic_tracking(1, n=40)
    t2 = _synthetic_tracking(2, n=40)
    t2["frames"] = [
        {**f, "track_id": 2, "bbox": [400.0 + i, 200.0, 450.0 + i, 280.0]}
        for i, f in enumerate(t2["frames"])
    ]
    merged = {
        "fps": 25.0,
        "width": 1280,
        "height": 720,
        "frames": t1["frames"] + t2["frames"],
    }
    summary = build_metrics_summary(
        video_id="test-vid",
        match_type="doubles",
        target_track_ids=[1, 2],
        tracking=merged,
        duration_sec=40 / 25,
    )
    assert summary.doubles is not None
    assert len(summary.doubles.players) == 2
