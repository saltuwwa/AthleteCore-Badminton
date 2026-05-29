"""Tests for singles target resolution by court_side."""

from __future__ import annotations

import pytest

from video_analysis.target_resolution import resolve_singles_target_tracks


def _tracking_with_sides() -> dict:
    frames = []
    for fi in range(20):
        frames.append(
            {
                "frame_index": fi,
                "timestamp_sec": fi / 25.0,
                "track_id": 268,
                "bbox": [900, 520, 1020, 720],
                "confidence": 0.9,
                "keypoints": [[0.5, 0.5, 0.9] * 3] * 17,
            }
        )
        frames.append(
            {
                "frame_index": fi + 100,
                "timestamp_sec": (fi + 100) / 25.0,
                "track_id": 94,
                "bbox": [520, 200, 680, 480],
                "confidence": 0.85,
                "keypoints": [[0.5, 0.5, 0.9] * 3] * 17,
            }
        )
    return {"width": 1280, "height": 864, "fps": 25.0, "frames": frames}


def test_resolve_far_target_not_first_id():
    resolved = resolve_singles_target_tracks(
        _tracking_with_sides(),
        [268, 94],
        target_court_side="far",
        target_label="Miyazaki",
    )
    assert resolved["target_player_id"] == 94
    assert resolved["opponent_player_id"] == 268
    assert resolved["target_track_ids"] == [94]
    assert resolved["target_label"] == "Miyazaki"
    assert resolved["target_court_side"] == "far"


def test_resolve_near_target():
    resolved = resolve_singles_target_tracks(
        _tracking_with_sides(),
        [268, 94],
        target_court_side="near",
    )
    assert resolved["target_player_id"] == 268
    assert resolved["opponent_player_id"] == 94


def test_single_id_unchanged():
    resolved = resolve_singles_target_tracks(_tracking_with_sides(), [268], target_court_side="near")
    assert resolved["target_player_id"] == 268
    assert resolved["target_track_ids"] == [268]
