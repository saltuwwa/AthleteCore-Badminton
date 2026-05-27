from __future__ import annotations

import math

from app.video_analysis.segment_filter import filter_gameplay_segments


def _keypoints(conf: float = 0.9) -> list[list[float]]:
    # Minimal COCO-like pose: 17 points with [x, y, conf]
    return [[0.0, 0.0, conf] for _ in range(17)]


def _bbox_from_center(
    *,
    cx: float,
    cy: float,
    w: float,
    h: float,
) -> list[float]:
    return [cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2]


def _tracking_payload(
    *,
    width: int,
    height: int,
    match_type: str,
    target_track_ids: list[int],
    timestamps: list[float],
    per_ts: dict[float, dict[int, dict]],
) -> dict:
    frames: list[dict] = []
    for ts in timestamps:
        bucket = per_ts.get(ts) or {}
        for tid, det in bucket.items():
            frames.append(
                {
                    "frame_index": int(ts * 25),
                    "timestamp_sec": float(ts),
                    "track_id": int(tid),
                    "bbox": det["bbox"],
                    "confidence": det.get("confidence", 0.9),
                    "keypoints": det.get("keypoints", _keypoints(0.9)),
                }
            )
    return {
        "frames": frames,
        "width": width,
        "height": height,
        "match_type": match_type,
        "target_track_ids": target_track_ids,
    }


def _eval_precision_recall(pred_valid: set[str], gt_valid: set[str]) -> tuple[float, float]:
    if not pred_valid:
        return 0.0, 0.0
    if not gt_valid:
        return 0.0, 0.0
    tp = len(pred_valid & gt_valid)
    precision = tp / len(pred_valid)
    recall = tp / len(gt_valid)
    return precision, recall


def test_normal_gameplay_segments():
    # Singles: 2 players visible (tids 1 target, 2 opponent)
    width, height = 1000, 700
    timestamps = [0, 1, 2, 3, 4]
    per_ts = {}
    for ts in timestamps:
        per_ts[ts] = {
            1: {"bbox": _bbox_from_center(cx=350 + 40 * ts, cy=380, w=180, h=260)},
            2: {"bbox": _bbox_from_center(cx=520 + 40 * ts, cy=390, w=180, h=260)},
        }
    payload = _tracking_payload(
        width=width,
        height=height,
        match_type="singles",
        target_track_ids=[1],
        timestamps=timestamps,
        per_ts=per_ts,
    )

    res = filter_gameplay_segments(payload)
    pred_valid = set(res["valid_timestamp_keys"])
    gt_valid = {f"{t:.2f}" for t in timestamps}

    precision, recall = _eval_precision_recall(pred_valid, gt_valid)
    assert precision == 1.0
    assert recall == 1.0
    assert res["valid_gameplay_ratio"] == 1.0


def test_replay_or_slow_motion_is_ignored():
    width, height = 1000, 700
    timestamps = [0, 1, 2, 3, 4, 5]

    per_ts = {}
    # Valid gameplay: moderate movement, normal bbox sizes
    for ts in [0, 1, 2]:
        per_ts[ts] = {
            1: {"bbox": _bbox_from_center(cx=350 + 40 * ts, cy=380, w=180, h=260)},
            2: {"bbox": _bbox_from_center(cx=520 + 40 * ts, cy=390, w=180, h=260)},
        }
    # Replay: very low movement + bbox area "scene change" (close-up-like)
    for ts in [3, 4, 5]:
        per_ts[ts] = {
            1: {"bbox": _bbox_from_center(cx=380 + 6 * (ts - 3), cy=380, w=450, h=380)},
            2: {"bbox": _bbox_from_center(cx=560 + 6 * (ts - 3), cy=390, w=450, h=380)},
        }

    payload = _tracking_payload(
        width=width,
        height=height,
        match_type="singles",
        target_track_ids=[1],
        timestamps=timestamps,
        per_ts=per_ts,
    )

    res = filter_gameplay_segments(payload)
    pred_valid = set(res["valid_timestamp_keys"])
    gt_replay = {f"{t:.2f}" for t in [3, 4, 5]}

    # Replay timestamps must not be considered valid gameplay.
    assert pred_valid.isdisjoint(gt_replay)
    reasons = {seg["reason"] for seg in res["ignored_segments"]}
    assert "replay_or_slow_motion" in reasons


def test_coach_or_spectator_view_is_ignored():
    width, height = 1000, 700
    timestamps = [0, 1, 2, 3, 4]
    per_ts = {}

    # Gameplay until 2
    for ts in [0, 1, 2]:
        per_ts[ts] = {
            1: {"bbox": _bbox_from_center(cx=360 + 35 * ts, cy=380, w=180, h=260)},
            2: {"bbox": _bbox_from_center(cx=520 + 35 * ts, cy=390, w=180, h=260)},
        }
    # Coach/spectator: boxes outside court margins
    for ts in [3, 4]:
        per_ts[ts] = {
            1: {"bbox": _bbox_from_center(cx=20, cy=50, w=180, h=260)},
            2: {"bbox": _bbox_from_center(cx=60, cy=60, w=180, h=260)},
        }

    payload = _tracking_payload(
        width=width,
        height=height,
        match_type="singles",
        target_track_ids=[1],
        timestamps=timestamps,
        per_ts=per_ts,
    )
    res = filter_gameplay_segments(payload)
    pred_valid = set(res["valid_timestamp_keys"])
    gt_invalid = {f"{t:.2f}" for t in [3, 4]}
    assert pred_valid.isdisjoint(gt_invalid)


def test_closeup_is_ignored():
    width, height = 1000, 700
    timestamps = [0, 1, 2, 3]
    per_ts = {}

    # Gameplay first 2
    for ts in [0, 1]:
        per_ts[ts] = {
            1: {"bbox": _bbox_from_center(cx=360 + 45 * ts, cy=380, w=180, h=260)},
            2: {"bbox": _bbox_from_center(cx=520 + 45 * ts, cy=390, w=180, h=260)},
        }
    # Close-up: very large bbox areas
    for ts in [2, 3]:
        per_ts[ts] = {
            1: {"bbox": _bbox_from_center(cx=420, cy=380, w=520, h=520)},
            2: {"bbox": _bbox_from_center(cx=560, cy=390, w=520, h=520)},
        }

    payload = _tracking_payload(
        width=width,
        height=height,
        match_type="singles",
        target_track_ids=[1],
        timestamps=timestamps,
        per_ts=per_ts,
    )
    res = filter_gameplay_segments(payload)
    pred_valid = set(res["valid_timestamp_keys"])
    gt_closeup = {f"{t:.2f}" for t in [2, 3]}
    assert pred_valid.isdisjoint(gt_closeup)
    reasons = {seg["reason"] for seg in res["ignored_segments"]}
    assert "closeup" in reasons


def test_scoreboard_is_ignored():
    width, height = 1000, 700
    timestamps = [0, 1, 2]
    per_ts = {}
    # Gameplay for 0
    per_ts[0] = {
        1: {"bbox": _bbox_from_center(cx=360, cy=380, w=180, h=260), "keypoints": _keypoints(0.9)},
        2: {"bbox": _bbox_from_center(cx=520, cy=390, w=180, h=260), "keypoints": _keypoints(0.9)},
    }
    # Scoreboard-like: missing keypoints (pose not available)
    for ts in [1, 2]:
        per_ts[ts] = {
            1: {"bbox": _bbox_from_center(cx=500, cy=300, w=220, h=240), "keypoints": []},
            2: {"bbox": _bbox_from_center(cx=650, cy=320, w=220, h=240), "keypoints": []},
        }

    payload = _tracking_payload(
        width=width,
        height=height,
        match_type="singles",
        target_track_ids=[1],
        timestamps=timestamps,
        per_ts=per_ts,
    )
    res = filter_gameplay_segments(payload)
    pred_valid = set(res["valid_timestamp_keys"])
    gt_invalid = {f"{t:.2f}" for t in [1, 2]}
    assert pred_valid.isdisjoint(gt_invalid)
    reasons = {seg["reason"] for seg in res["ignored_segments"]}
    assert "scoreboard" in reasons


def test_pause_is_ignored():
    width, height = 1000, 700
    timestamps = [0, 1, 2, 3, 4]
    per_ts = {}

    # Normal gameplay for 0-1
    for ts in [0, 1]:
        per_ts[ts] = {
            1: {"bbox": _bbox_from_center(cx=360 + 45 * ts, cy=380, w=180, h=260)},
            2: {"bbox": _bbox_from_center(cx=520 + 45 * ts, cy=390, w=180, h=260)},
        }
    # Pause 2-4: enough players and court visible, but movement is too small
    for ts in [2, 3, 4]:
        per_ts[ts] = {
            1: {"bbox": _bbox_from_center(cx=450 + 5 * (ts - 2), cy=380, w=180, h=260)},
            2: {"bbox": _bbox_from_center(cx=610 + 5 * (ts - 2), cy=390, w=180, h=260)},
        }

    payload = _tracking_payload(
        width=width,
        height=height,
        match_type="singles",
        target_track_ids=[1],
        timestamps=timestamps,
        per_ts=per_ts,
    )
    res = filter_gameplay_segments(payload)
    pred_valid = set(res["valid_timestamp_keys"])
    gt_pause = {f"{t:.2f}" for t in [2, 3, 4]}
    assert pred_valid.isdisjoint(gt_pause)
    reasons = {seg["reason"] for seg in res["ignored_segments"]}
    assert "pause" in reasons


def test_mixed_video_valid_and_invalid_segments_eval_metrics():
    width, height = 1000, 700
    timestamps = list(range(0, 12))  # 0..11 seconds
    per_ts = {}

    gt_valid = set()
    gt_replay = set()
    gt_invalid = set()

    # Valid: 0-3
    for ts in [0, 1, 2, 3]:
        gt_valid.add(ts)
        per_ts[ts] = {
            1: {"bbox": _bbox_from_center(cx=350 + 40 * ts, cy=380, w=180, h=260)},
            2: {"bbox": _bbox_from_center(cx=520 + 40 * ts, cy=390, w=180, h=260)},
        }
    # Replay: 4-6
    for ts in [4, 5, 6]:
        gt_replay.add(ts)
        gt_invalid.add(ts)
        per_ts[ts] = {
            1: {"bbox": _bbox_from_center(cx=380 + 6 * (ts - 4), cy=380, w=450, h=380)},
            2: {"bbox": _bbox_from_center(cx=560 + 6 * (ts - 4), cy=390, w=450, h=380)},
        }
    # Pause: 7-8
    for ts in [7, 8]:
        gt_invalid.add(ts)
        per_ts[ts] = {
            1: {"bbox": _bbox_from_center(cx=450 + 5 * (ts - 7), cy=380, w=180, h=260)},
            2: {"bbox": _bbox_from_center(cx=610 + 5 * (ts - 7), cy=390, w=180, h=260)},
        }
    # Valid: 9-11
    for ts in [9, 10, 11]:
        gt_valid.add(ts)
        per_ts[ts] = {
            1: {"bbox": _bbox_from_center(cx=350 + 40 * ts, cy=380, w=180, h=260)},
            2: {"bbox": _bbox_from_center(cx=520 + 40 * ts, cy=390, w=180, h=260)},
        }

    payload = _tracking_payload(
        width=width,
        height=height,
        match_type="singles",
        target_track_ids=[1],
        timestamps=timestamps,
        per_ts=per_ts,
    )

    res = filter_gameplay_segments(payload)
    pred_valid = set(res["valid_timestamp_keys"])
    gt_valid_keys = {f"{t:.2f}" for t in gt_valid}
    gt_invalid_keys = {f"{t:.2f}" for t in gt_invalid}
    gt_replay_keys = {f"{t:.2f}" for t in gt_replay}

    precision, recall = _eval_precision_recall(pred_valid, gt_valid_keys)
    assert precision >= 0.85
    assert recall >= 0.85

    ignored_replay_rate = (
        1.0 - (len(gt_replay_keys & pred_valid) / max(1, len(gt_replay_keys)))
    )
    invalid_segment_leak_rate = (
        len(pred_valid & gt_invalid_keys) / max(1, len(gt_invalid_keys))
    )
    assert ignored_replay_rate >= 0.8
    assert invalid_segment_leak_rate <= 0.2
    assert res["analysis_confidence"] >= 0.5

    # Sanity: returned ratio should match predicted valid / total
    expected_ratio = len(pred_valid) / len(timestamps)
    assert math.isclose(res["valid_gameplay_ratio"], round(expected_ratio, 3), rel_tol=0.0, abs_tol=1e-3)


def test_doubles_requires_four_players_and_selected_pair_visible():
    width, height = 1000, 700
    timestamps = [0, 1, 2, 3]
    per_ts = {}

    target_ids = [1, 3]
    # Valid frames: 4 players in court, pair visible
    for ts in [0, 1]:
        per_ts[ts] = {
            1: {"bbox": _bbox_from_center(cx=300 + 35 * ts, cy=380, w=170, h=250)},
            2: {"bbox": _bbox_from_center(cx=460 + 35 * ts, cy=410, w=170, h=250)},
            3: {"bbox": _bbox_from_center(cx=600 + 35 * ts, cy=380, w=170, h=250)},
            4: {"bbox": _bbox_from_center(cx=760 + 35 * ts, cy=410, w=170, h=250)},
        }
    # Invalid frames: remove player 3 (selected team not visible)
    for ts in [2, 3]:
        per_ts[ts] = {
            1: {"bbox": _bbox_from_center(cx=320 + 30 * ts, cy=380, w=170, h=250)},
            2: {"bbox": _bbox_from_center(cx=480 + 30 * ts, cy=410, w=170, h=250)},
            4: {"bbox": _bbox_from_center(cx=760 + 30 * ts, cy=410, w=170, h=250)},
        }

    payload = _tracking_payload(
        width=width,
        height=height,
        match_type="doubles",
        target_track_ids=target_ids,
        timestamps=timestamps,
        per_ts=per_ts,
    )

    res = filter_gameplay_segments(payload)
    pred_valid = set(res["valid_timestamp_keys"])
    gt_valid = {f"{t:.2f}" for t in [0, 1]}
    gt_invalid = {f"{t:.2f}" for t in [2, 3]}

    assert pred_valid == gt_valid

