"""Tests for video debug reporter (no GPU)."""

from __future__ import annotations

import json

from video_analysis.debug_report import VideoDebugReporter, debug_report_dir, load_debug_bundle, redact_secrets


def test_debug_reporter_writes_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "video_analysis.debug_report.DEBUG_ROOT",
        tmp_path / "video_debug",
    )
    rep = VideoDebugReporter("vid-test", enabled=True)
    with rep.step("metadata"):
        rep.write("01_video_metadata.json", {"filename": "x.mp4"})
    idx = rep.finalize()
    assert idx["debug_report_id"] == "vid-test"
    bundle = load_debug_bundle("vid-test")
    assert bundle["01_video_metadata"]["filename"] == "x.mp4"
    assert (debug_report_dir("vid-test") / "12_timing_report.json").is_file()


def test_redact_secrets():
    data = {"api_key": "sk-abcdefghijklmnop", "nested": {"token": "secret"}}
    out = redact_secrets(data)
    assert out["api_key"] == "***REDACTED***"
    assert out["nested"]["token"] == "***REDACTED***"
