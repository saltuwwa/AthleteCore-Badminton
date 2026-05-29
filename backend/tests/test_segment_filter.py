"""Tests for gameplay segment filtering."""

from __future__ import annotations

import pytest

from video_analysis.eval_report import build_video_eval_report, compute_segment_eval_metrics
from video_analysis.segment_filter import (
    FrameDetections,
    classify_frame_context,
    detect_replay_or_slowmo,
    filter_gameplay_segments,
    is_valid_gameplay_frame,
)


def _kp(visible: bool = True) -> list[list[float]]:
    base = [0.5, 0.5, 0.9 if visible else 0.1] * 17
    return [base[i : i + 3] for i in range(0, 51, 3)]


def _court_bbox(cx: float, cy: float, size: float = 0.12) -> tuple[float, float, float, float]:
    w, h = 1280.0, 720.0
    bw, bh = w * size, h * size
    return (cx * w - bw / 2, cy * h - bh / 2, cx * w + bw / 2, cy * h + bh / 2)


def _frame(
    frame_index: int,
    *,
    players: list[tuple[int, tuple[float, float, float, float]]],
    ts: float | None = None,
) -> list[dict]:
    out = []
    for tid, bbox in players:
        out.append(
            {
                "frame_index": frame_index,
                "timestamp_sec": ts if ts is not None else frame_index / 25.0,
                "track_id": tid,
                "bbox": list(bbox),
                "confidence": 0.9,
                "keypoints": _kp(),
            }
        )
    return out


def _gameplay_singles_frames(n: int = 20, *, target_id: int = 1) -> list[dict]:
    frames: list[dict] = []
    for i in range(n):
        frames.extend(
            _frame(
                i,
                players=[
                    (target_id, _court_bbox(0.4, 0.5)),
                    (2, _court_bbox(0.6, 0.5)),
                ],
            )
        )
    return frames


def test_classify_normal_gameplay():
    fd = FrameDetections(
        track_ids=[1, 2],
        bboxes=[_court_bbox(0.4, 0.5), _court_bbox(0.6, 0.5)],
        keypoints=[_kp(), _kp()],
    )
    assert classify_frame_context(None, fd, width=1280, height=720) == "gameplay"


def test_classify_closeup():
    fd = FrameDetections(
        track_ids=[1],
        bboxes=[(50, 50, 1200, 680)],
        keypoints=[_kp()],
    )
    assert classify_frame_context(None, fd, width=1280, height=720) == "closeup"


def test_classify_coach_spectator():
    fd = FrameDetections(
        track_ids=[9],
        bboxes=[(10, 200, 60, 500)],
        keypoints=[_kp()],
    )
    assert classify_frame_context(None, fd, width=1280, height=720) == "coach_or_spectator"


def test_classify_pause():
    assert classify_frame_context(None, FrameDetections(), width=1280, height=720) == "pause"


def test_classify_scoreboard():
    fd = FrameDetections(
        track_ids=[],
        bboxes=[],
        keypoints=[],
    )
    assert classify_frame_context(None, fd, width=1280, height=720) == "pause"


def test_classify_replay_ocr():
    fd = FrameDetections(
        track_ids=[1, 2],
        bboxes=[_court_bbox(0.4, 0.5), _court_bbox(0.6, 0.5)],
        keypoints=[_kp(), _kp()],
    )
    assert (
        classify_frame_context(None, fd, width=1280, height=720, ocr_text="INSTANT REPLAY")
        == "replay"
    )


def test_is_valid_gameplay_frame_singles():
    fd = FrameDetections(
        track_ids=[1, 2],
        bboxes=[_court_bbox(0.4, 0.5), _court_bbox(0.6, 0.5)],
        keypoints=[_kp(), _kp()],
    )
    assert is_valid_gameplay_frame(None, fd, "singles", [1], width=1280, height=720)


def test_is_valid_rejects_closeup():
    fd = FrameDetections(track_ids=[1], bboxes=[(50, 50, 1200, 680)], keypoints=[_kp()])
    assert not is_valid_gameplay_frame(None, fd, "singles", [1], width=1280, height=720)


def test_detect_replay_slowmo():
    from video_analysis.segment_filter import FrameRecord

    seg = []
    for i in range(10):
        if i < 5:
            bbox = _court_bbox(0.5, 0.5, 0.1)
        else:
            bbox = (50, 50, 1200, 680)
        seg.append(
            FrameRecord(
                frame_index=i,
                timestamp_sec=i / 25.0,
                detections=FrameDetections(track_ids=[1], bboxes=[bbox], keypoints=[_kp()]),
            )
        )
    assert detect_replay_or_slowmo(seg, width=1280, height=720)


def test_filter_mixed_video_segments():
    frames: list[dict] = []
    frames.extend(_gameplay_singles_frames(15, target_id=1))
    for i in range(15, 20):
        frames.extend(
            _frame(i, players=[(1, (50, 50, 1200, 680))])
        )
    for i in range(20, 35):
        frames.extend(
            _frame(
                i,
                players=[
                    (1, _court_bbox(0.45, 0.5)),
                    (2, _court_bbox(0.55, 0.5)),
                ],
            )
        )

    result = filter_gameplay_segments(
        frames,
        match_type="singles",
        target_track_ids=[1],
        width=1280,
        height=720,
    )
    assert result["valid_gameplay_ratio"] > 0.5
    assert len(result["valid_segments"]) >= 1
    assert any(s.get("reason") for s in result["ignored_segments"])


def test_filter_low_ratio_warning():
    frames = []
    for i in range(10):
        frames.extend(_frame(i, players=[(1, (50, 50, 1200, 680))]))
    result = filter_gameplay_segments(
        frames, match_type="singles", target_track_ids=[1], width=1280, height=720
    )
    assert result["valid_gameplay_ratio"] < 0.25
    assert result["warning"] is not None


def test_filter_replay_segment_excluded():
    frames = _gameplay_singles_frames(10, target_id=1)
    for i in range(10, 18):
        frames.extend(_frame(i, players=[(1, (80, 80, 1180, 650))]))
    result = filter_gameplay_segments(
        frames, match_type="singles", target_track_ids=[1], width=1280, height=720
    )
    reasons = {s["reason"] for s in result["ignored_segments"]}
    assert "replay_or_slow_motion" in reasons or "closeup" in reasons


def test_filter_coach_spectator_excluded():
    frames = []
    for i in range(12):
        frames.extend(_frame(i, players=[(5, (5, 200, 55, 520))]))
    result = filter_gameplay_segments(
        frames, match_type="singles", target_track_ids=[5], width=1280, height=720
    )
    assert result["valid_gameplay_ratio"] == 0.0
    assert result["ignored_segments"]


def test_filter_scoreboard_context():
    fd = FrameDetections(
        track_ids=[1],
        bboxes=[(400, 5, 900, 55)],
        keypoints=[[]],
    )
    ctx = classify_frame_context(None, fd, width=1280, height=720)
    assert ctx in ("scoreboard", "pause", "unknown")


def test_eval_metrics_and_report():
    gt = {0, 1, 2, 3, 4}
    pred = {0, 1, 2, 5}
    m = compute_segment_eval_metrics(
        ground_truth_valid=gt,
        predicted_valid=pred,
        ground_truth_replay={10, 11},
        predicted_ignored_replay={10},
        all_frame_indices=set(range(15)),
        valid_gameplay_ratio=0.74,
        analysis_confidence=0.8,
    )
    assert 0 < m.gameplay_segment_precision <= 1
    assert m.valid_gameplay_ratio == 0.74

    report = build_video_eval_report(
        [
            {
                "name": "normal_gameplay",
                "ground_truth_valid": gt,
                "predicted_valid": pred,
                "all_frame_indices": set(range(15)),
            }
        ],
        segment_filter_summary={"valid_gameplay_ratio": 0.74, "analysis_confidence": 0.8},
    )
    assert "segment_filtering_quality" in report
    assert report["segment_filtering_quality"]["valid_gameplay_ratio"] == 0.74
