"""
Segment-filter evaluation metrics and video_eval_report builder.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Any


@dataclass
class SegmentEvalMetrics:
    gameplay_segment_precision: float
    gameplay_segment_recall: float
    ignored_replay_rate: float
    invalid_segment_leak_rate: float
    valid_gameplay_ratio: float
    analysis_confidence: float

    def to_dict(self) -> dict[str, float]:
        return {
            "gameplay_segment_precision": round(self.gameplay_segment_precision, 4),
            "gameplay_segment_recall": round(self.gameplay_segment_recall, 4),
            "ignored_replay_rate": round(self.ignored_replay_rate, 4),
            "invalid_segment_leak_rate": round(self.invalid_segment_leak_rate, 4),
            "valid_gameplay_ratio": round(self.valid_gameplay_ratio, 4),
            "analysis_confidence": round(self.analysis_confidence, 4),
        }


def compute_segment_eval_metrics(
    *,
    ground_truth_valid: set[int],
    predicted_valid: set[int],
    ground_truth_replay: set[int] | None = None,
    predicted_ignored_replay: set[int] | None = None,
    all_frame_indices: set[int] | None = None,
    valid_gameplay_ratio: float = 0.0,
    analysis_confidence: float = 0.0,
) -> SegmentEvalMetrics:
    """
    Frame-level precision/recall for gameplay classification.
    """
    gt_replay = ground_truth_replay or set()
    pred_replay = predicted_ignored_replay or set()
    universe = all_frame_indices or (ground_truth_valid | predicted_valid | gt_replay | pred_replay)

    tp = len(ground_truth_valid & predicted_valid)
    fp = len(predicted_valid - ground_truth_valid)
    fn = len(ground_truth_valid - predicted_valid)
    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0

    replay_gt = len(gt_replay)
    replay_correct = len(gt_replay & pred_replay)
    ignored_replay_rate = replay_correct / replay_gt if replay_gt else 1.0

    invalid_gt = universe - ground_truth_valid
    leaked = len(invalid_gt & predicted_valid)
    invalid_segment_leak_rate = leaked / len(invalid_gt) if invalid_gt else 0.0

    return SegmentEvalMetrics(
        gameplay_segment_precision=precision,
        gameplay_segment_recall=recall,
        ignored_replay_rate=ignored_replay_rate,
        invalid_segment_leak_rate=invalid_segment_leak_rate,
        valid_gameplay_ratio=valid_gameplay_ratio,
        analysis_confidence=analysis_confidence,
    )


def build_video_eval_report(
    cases: list[dict[str, Any]],
    *,
    segment_filter_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Aggregate per-case segment metrics into a video_eval_report payload.
    Each case: name, ground_truth_valid, predicted_valid, optional ground_truth_replay.
    """
    case_results: list[dict[str, Any]] = []
    agg_precision: list[float] = []
    agg_recall: list[float] = []
    agg_replay: list[float] = []
    agg_leak: list[float] = []

    for case in cases:
        m = compute_segment_eval_metrics(
            ground_truth_valid=set(case["ground_truth_valid"]),
            predicted_valid=set(case.get("predicted_valid", [])),
            ground_truth_replay=set(case.get("ground_truth_replay", [])),
            predicted_ignored_replay=set(case.get("predicted_ignored_replay", [])),
            all_frame_indices=set(case.get("all_frame_indices", [])),
            valid_gameplay_ratio=float(case.get("valid_gameplay_ratio", 0)),
            analysis_confidence=float(case.get("analysis_confidence", 0)),
        )
        case_results.append({"name": case["name"], "metrics": m.to_dict()})
        agg_precision.append(m.gameplay_segment_precision)
        agg_recall.append(m.gameplay_segment_recall)
        agg_replay.append(m.ignored_replay_rate)
        agg_leak.append(m.invalid_segment_leak_rate)

    def _avg(vals: list[float]) -> float:
        return round(mean(vals), 4) if vals else 0.0

    report: dict[str, Any] = {
        "segment_filtering_quality": {
            "gameplay_segment_precision": _avg(agg_precision),
            "gameplay_segment_recall": _avg(agg_recall),
            "ignored_replay_rate": _avg(agg_replay),
            "invalid_segment_leak_rate": _avg(agg_leak),
            "cases": case_results,
        },
    }
    if segment_filter_summary:
        report["segment_filtering_quality"]["valid_gameplay_ratio"] = segment_filter_summary.get(
            "valid_gameplay_ratio", 0
        )
        report["segment_filtering_quality"]["analysis_confidence"] = segment_filter_summary.get(
            "analysis_confidence", 0
        )
        report["last_run_segment_filter"] = segment_filter_summary
    return report
