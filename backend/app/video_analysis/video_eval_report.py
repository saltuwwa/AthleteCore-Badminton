from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class SegmentFilteringEval:
    gameplay_segment_precision: float
    gameplay_segment_recall: float
    ignored_replay_rate: float
    invalid_segment_leak_rate: float
    valid_gameplay_ratio: float
    analysis_confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "gameplay_segment_precision": self.gameplay_segment_precision,
            "gameplay_segment_recall": self.gameplay_segment_recall,
            "ignored_replay_rate": self.ignored_replay_rate,
            "invalid_segment_leak_rate": self.invalid_segment_leak_rate,
            "valid_gameplay_ratio": self.valid_gameplay_ratio,
            "analysis_confidence": self.analysis_confidence,
        }


def build_video_eval_report(*, segment_eval: SegmentFilteringEval) -> dict[str, Any]:
    # MVP: only segment filtering quality is reported yet.
    return {"segment_filtering": segment_eval.to_dict()}

