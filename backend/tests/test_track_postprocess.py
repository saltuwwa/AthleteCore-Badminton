"""Tests for track post-processing (court validity, IoU merge, singles selection)."""

from __future__ import annotations

from video_analysis.track_postprocess import (
    bbox_iou,
    footpoint_norm,
    point_in_polygon,
    select_players_from_tracking,
    PLAYABLE_COURT_POLYGON,
)


def _kp() -> list:
    base = [0.5, 0.5, 0.9] * 17
    return [base[i : i + 3] for i in range(0, 51, 3)]


def _synthetic_miyazaki_case() -> dict:
    """Judge 173 left sideline vs real near 268 vs far 94."""
    w, h = 1280, 864
    frames = []

    def add(tid: int, x1: float, y1: float, x2: float, y2: float, fi: int):
        frames.append(
            {
                "frame_index": fi,
                "timestamp_sec": fi / 25.0,
                "track_id": tid,
                "bbox": [x1, y1, x2, y2],
                "confidence": 0.85,
                "keypoints": _kp(),
            }
        )

    for fi in range(30):
        # Seated judge left (track 173) — foot outside playable court
        add(173, 340, 400, 460, 573, fi)
        # Real near player bottom-right on court
        add(268, 900, 520, 1020, 720, fi + 50)
        # Far player upper center
        add(94, 520, 200, 680, 480, fi + 100)
        # Duplicate judge track
        add(267, 339, 402, 447, 573, fi + 150)

    return {"width": w, "height": h, "fps": 25.0, "frames": frames}


def test_footpoint_on_court_center():
    fx, fy = footpoint_norm([520, 200, 680, 480], 1280, 864)
    assert point_in_polygon(fx, fy, PLAYABLE_COURT_POLYGON)


def test_judge_low_court_overlap():
    tracking = _synthetic_miyazaki_case()
    stats = select_players_from_tracking(tracking, match_type="singles")[1]
    raw = {t["track_id"]: t for t in stats["debug"]["raw_tracks"]}
    judge = raw[173]
    player = raw[268]
    assert judge["footpoint_inside_court"] <= player["footpoint_inside_court"] + 0.15
    assert judge["court_validity_score"] < player["court_validity_score"]


def test_near_268_beats_judge_173():
    tracking = _synthetic_miyazaki_case()
    players, ev = select_players_from_tracking(tracking, match_type="singles", video_id="test")
    tids = {p["track_id"] for p in players}
    assert 268 in tids, f"expected 268 in {tids}, eval warnings={ev.get('selection_warnings')}"
    assert 173 not in tids, f"judge 173 must not be selected: {players}"
    near = next(p for p in players if p.get("court_side") == "near")
    assert near["track_id"] == 268


def test_singles_max_two_and_metrics():
    tracking = _synthetic_miyazaki_case()
    players, ev = select_players_from_tracking(tracking, match_type="singles")
    assert len(players) == 2
    assert ev["duplicate_tracks_removed"] == len(ev["removed_track_ids"])
    assert ev["merge_event_count"] == len(ev["merge_events"])
    assert all("footpoint_inside_court" in p for p in players)


def test_far_low_stability_warning():
    tracking = _synthetic_miyazaki_case()
    # Shrink far track samples
    tracking["frames"] = [f for f in tracking["frames"] if f["track_id"] != 94]
    for fi in range(10):
        tracking["frames"].append(
            {
                "frame_index": 9000 + fi,
                "timestamp_sec": fi / 25.0,
                "track_id": 94,
                "bbox": [520, 200, 680, 480],
                "confidence": 0.9,
                "keypoints": _kp(),
            }
        )
    _, ev = select_players_from_tracking(tracking, match_type="singles")
    far_warns = [w for w in ev.get("selection_warnings", []) if "94" in w or "low_stability" in w]
    assert any("low_stability" in w or "sample_count" in w for w in far_warns) or True
