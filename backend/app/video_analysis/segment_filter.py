from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, TypedDict


GameplayContext = Literal[
    "gameplay",
    "replay",
    "coach_or_spectator",
    "closeup",
    "scoreboard",
    "pause",
    "unknown",
]


class DetBox(TypedDict, total=False):
    x1: float
    y1: float
    x2: float
    y2: float


class PosePoint(TypedDict, total=False):
    # YOLO-style keypoint: [x, y, conf]
    # We only need conf to decide if pose is present.
    c: float


class DetFrame(TypedDict, total=False):
    # Per-timestamp "frame" in our filter pipeline.
    timestamp_sec: float
    frame_index: int
    width: int
    height: int
    # Derived features for heuristics
    movement_speed_est: float
    avg_bbox_area_ratio: float
    court_visible_ratio: float
    keypoints_ok_ratio: float
    replay_candidate: bool


class Detection(TypedDict, total=False):
    track_id: int
    bbox: DetBox
    confidence: float
    keypoints: list[list[float]]


def _bbox_center(b: DetBox) -> tuple[float, float]:
    x1, y1, x2, y2 = float(b["x1"]), float(b["y1"]), float(b["x2"]), float(b["y2"])
    return (x1 + x2) / 2.0, (y1 + y2) / 2.0


def _bbox_area(b: DetBox) -> float:
    x1, y1, x2, y2 = float(b["x1"]), float(b["y1"]), float(b["x2"]), float(b["y2"])
    return max(0.0, (x2 - x1)) * max(0.0, (y2 - y1))


def _keypoints_pose_ok(keypoints: list[list[float]] | None) -> bool:
    if not keypoints:
        return False
    # Expect COCO pose ~17 keypoints; tolerate missing.
    if len(keypoints) < 5:
        return False
    confs: list[float] = []
    for kp in keypoints:
        if len(kp) >= 3:
            confs.append(float(kp[2]))
    if not confs:
        return False
    return sum(confs) / len(confs) >= 0.35


def _format_mmss(ts_sec: float) -> str:
    if ts_sec < 0:
        ts_sec = 0
    m = int(ts_sec // 60)
    s = int(ts_sec - m * 60)
    return f"{m:02d}:{s:02d}"


@dataclass(slots=True)
class Segment:
    start_sec: float
    end_sec: float
    reason: str | None = None

    @property
    def start(self) -> str:
        return _format_mmss(self.start_sec)

    @property
    def end(self) -> str:
        return _format_mmss(self.end_sec)


class FilterResult(TypedDict):
    valid_segments: list[dict[str, str]]
    ignored_segments: list[dict[str, str]]
    valid_gameplay_ratio: float
    warning: str | None
    analysis_confidence: float
    # Extra internal hint for downstream: which timestamps are safe.
    valid_timestamp_keys: list[str]


# Heuristic thresholds (tuned for MVP synthetic tests + safety-first filtering)
COURT_X_MIN = 0.06
COURT_X_MAX = 0.94
COURT_Y_MIN = 0.08
COURT_Y_MAX = 0.92

CLOSEUP_BBOX_AREA_RATIO = 0.22
PAUSE_SPEED_NORM = 0.016
REPLAY_SPEED_NORM = 0.010


def classify_frame_context(
    frame: DetFrame,
    detections: list[Detection],
) -> GameplayContext:
    """
    Heuristic classification for a single timestamp frame.

    `frame` may include derived fields:
    - movement_speed_est
    - replay_candidate
    - court_visible_ratio
    - keypoints_ok_ratio
    - avg_bbox_area_ratio
    """
    replay_candidate = bool(frame.get("replay_candidate"))
    if replay_candidate:
        return "replay"

    court_visible_ratio = float(frame.get("court_visible_ratio", 0.0) or 0.0)
    keypoints_ok_ratio = float(frame.get("keypoints_ok_ratio", 0.0) or 0.0)
    avg_bbox_area_ratio = float(frame.get("avg_bbox_area_ratio", 0.0) or 0.0)

    if not detections:
        return "unknown"

    if avg_bbox_area_ratio >= CLOSEUP_BBOX_AREA_RATIO and court_visible_ratio > 0.2:
        return "closeup"

    if keypoints_ok_ratio < 0.15:
        # Often scoreboard-like shots: keypoints absent / missing pose.
        return "scoreboard"

    if court_visible_ratio < 0.45:
        return "coach_or_spectator"

    movement_speed = float(frame.get("movement_speed_est", 999.0))
    if movement_speed < PAUSE_SPEED_NORM and court_visible_ratio >= 0.45:
        return "pause"

    return "gameplay"


def _expected_total_players(match_type: str) -> int:
    return 2 if match_type == "singles" else 4


def is_valid_gameplay_frame(
    frame: DetFrame,
    detections: list[Detection],
    match_type: str,
    target_track_ids: list[int],
) -> bool:
    if not detections:
        return False

    ctx = classify_frame_context(frame, detections)
    if ctx != "gameplay":
        # Strict safety-first: only "gameplay" frames may contribute to metrics.
        return False

    expected = _expected_total_players(match_type)

    width = int(frame.get("width") or 0)
    height = int(frame.get("height") or 0)
    if width <= 0 or height <= 0:
        return False

    # Enough players detected (in-court).
    in_court = 0
    pose_ok = 0
    target_ids = set(int(t) for t in (target_track_ids or []))
    target_visible_ids: set[int] = set()

    for d in detections:
        bbox = d.get("bbox")
        if not bbox:
            continue
        cx, cy = _bbox_center(bbox)
        x_ok = (cx / width) >= COURT_X_MIN and (cx / width) <= COURT_X_MAX
        y_ok = (cy / height) >= COURT_Y_MIN and (cy / height) <= COURT_Y_MAX
        if x_ok and y_ok:
            in_court += 1
            if _keypoints_pose_ok(d.get("keypoints")):
                pose_ok += 1
        tid = d.get("track_id")
        if tid in target_ids and x_ok and y_ok:
            if _keypoints_pose_ok(d.get("keypoints")):
                target_visible_ids.add(int(tid))

    if in_court < expected:
        return False
    if pose_ok < expected - 1:
        return False
    if match_type == "singles":
        if not target_visible_ids:
            return False
    else:
        # For doubles/mixed, require the selected team to be visible.
        if not target_ids or target_visible_ids != target_ids:
            return False

    # If we got here, the selected target(s) and required pose are visible.
    if len(target_ids) == 0:
        return False

    # Tracking stability is represented indirectly via movement_speed_est:
    # for gameplay we expect movement not extremely small.
    if float(frame.get("movement_speed_est", 0.0)) < PAUSE_SPEED_NORM:
        return False

    return True


def detect_replay_or_slowmo(segment: list[DetFrame]) -> bool:
    """
    Replay/slow-motion heuristics on a segment (list of timestamp frames).
    """
    if len(segment) < 3:
        return False

    speeds = [float(f.get("movement_speed_est", 999.0)) for f in segment]
    court_ratios = [float(f.get("court_visible_ratio", 0.0) or 0.0) for f in segment]
    area_ratios = [float(f.get("avg_bbox_area_ratio", 0.0) or 0.0) for f in segment]

    avg_speed = sum(speeds) / len(speeds)
    min_speed = min(speeds)
    avg_court = sum(court_ratios) / len(court_ratios)
    max_area = max(area_ratios)

    # Scene change proxy: bbox area jump (court -> close-up) while movement stays tiny.
    area_change = max_area - min(area_ratios)

    # Safety-first: mark as replay when movement is very low AND at least one of:
    #  - court ratio drops
    #  - close-up-like bbox area appears
    if avg_speed <= REPLAY_SPEED_NORM and (
        avg_court <= 0.7 or max_area >= CLOSEUP_BBOX_AREA_RATIO or area_change >= 0.10
    ):
        return True

    # Repeated similar motion pattern proxy: near-constant speed.
    mean = avg_speed
    var = sum((s - mean) ** 2 for s in speeds) / max(1, len(speeds))
    if avg_speed <= REPLAY_SPEED_NORM and math.sqrt(var) <= 0.003 and max_area >= 0.15:
        return True

    return False


def _timestamp_key(ts_sec: float) -> str:
    # Group by near-identical frames. Timestamp comes rounded from tracking payload.
    return f"{ts_sec:.2f}"


def _compute_movement_speed_norm(
    prev_dets: list[Detection],
    curr_dets: list[Detection],
    *,
    width: int,
    height: int,
) -> float:
    diag = math.sqrt(width * width + height * height) or 1.0
    # Average centroid displacement for matching track_ids.
    prev_map = {int(d.get("track_id")): d for d in prev_dets if d.get("track_id") is not None}
    curr_map = {int(d.get("track_id")): d for d in curr_dets if d.get("track_id") is not None}
    common = sorted(set(prev_map.keys()) & set(curr_map.keys()))
    if not common:
        return 0.0
    disps: list[float] = []
    for tid in common:
        pb = prev_map[tid].get("bbox")
        cb = curr_map[tid].get("bbox")
        if not pb or not cb:
            continue
        px, py = _bbox_center(pb)
        cx, cy = _bbox_center(cb)
        dist = math.sqrt((cx - px) ** 2 + (cy - py) ** 2)
        disps.append(dist / diag)
    if not disps:
        return 0.0
    # We normalize by dt implicitly elsewhere; as MVP, assume ~1 sec between grouped timestamps.
    return float(sum(disps) / len(disps))


def filter_gameplay_segments(tracked_frames: Any) -> FilterResult:
    """
    Filter tracked frames into gameplay vs replay/coach/closeup/scoreboard/pause.

    Input expected:
    {
      "frames": [ ... per-detection per timestamp ... ],
      "width": int,
      "height": int,
      "match_type": "singles" | "doubles" | "mixed",
      "target_track_ids": [int]
    }
    """
    if not isinstance(tracked_frames, dict) or "frames" not in tracked_frames:
        raise ValueError("tracked_frames must be a dict with 'frames'")

    frames_list = tracked_frames.get("frames") or []
    width = int(tracked_frames.get("width") or 0)
    height = int(tracked_frames.get("height") or 0)
    match_type = str(tracked_frames.get("match_type") or "singles")
    target_track_ids = list(tracked_frames.get("target_track_ids") or [])

    # Group by timestamp.
    by_ts: dict[str, dict[str, Any]] = {}
    for fr in frames_list:
        ts = float(fr.get("timestamp_sec") or 0.0)
        k = _timestamp_key(ts)
        width_ = fr.get("width") if fr.get("width") else width
        height_ = fr.get("height") if fr.get("height") else height
        if k not in by_ts:
            by_ts[k] = {
                "timestamp_sec": ts,
                "frame_index": int(fr.get("frame_index") or 0),
                "width": int(width_ or 0),
                "height": int(height_ or 0),
                "detections": [],
            }
        det: Detection = {
            "track_id": int(fr.get("track_id")),
            "bbox": {
                "x1": float(fr["bbox"][0]),
                "y1": float(fr["bbox"][1]),
                "x2": float(fr["bbox"][2]),
                "y2": float(fr["bbox"][3]),
            },
            "confidence": float(fr.get("confidence") or 0.0),
            "keypoints": fr.get("keypoints") or [],
        }
        by_ts[k]["detections"].append(det)

    ts_keys = sorted(by_ts.keys(), key=lambda x: float(x))
    timestamp_frames: list[DetFrame] = []

    prev_dets: list[Detection] | None = None
    prev_ts: float | None = None
    for k in ts_keys:
        obj = by_ts[k]
        ts = float(obj["timestamp_sec"])
        dets = obj["detections"]
        court_visible_ratio = _court_visible_ratio(obj["width"], obj["height"], dets)
        keypoints_ok_ratio = _keypoints_ok_ratio(dets)
        area_ratio = _avg_bbox_area_ratio(obj["width"], obj["height"], dets)

        dt = 1.0
        if prev_ts is not None:
            dt = max(ts - prev_ts, 1e-6)

        movement = 0.0
        if prev_dets is not None:
            # Normalize by dt explicitly.
            movement = _compute_movement_speed_norm(prev_dets, dets, width=obj["width"], height=obj["height"]) / dt

        timestamp_frames.append(
            {
                "timestamp_sec": ts,
                "frame_index": int(obj["frame_index"]),
                "width": int(obj["width"]),
                "height": int(obj["height"]),
                "movement_speed_est": float(movement),
                "avg_bbox_area_ratio": float(area_ratio),
                "court_visible_ratio": float(court_visible_ratio),
                "keypoints_ok_ratio": float(keypoints_ok_ratio),
                "replay_candidate": False,
            }
        )

        prev_dets = dets
        prev_ts = ts

    # Detect low-motion spans and decide replay vs pause.
    i = 0
    while i < len(timestamp_frames):
        if float(timestamp_frames[i].get("movement_speed_est", 999.0)) > PAUSE_SPEED_NORM:
            i += 1
            continue

        j = i
        while (
            j < len(timestamp_frames)
            and float(timestamp_frames[j].get("movement_speed_est", 999.0)) <= PAUSE_SPEED_NORM
        ):
            j += 1

        span = timestamp_frames[i:j]
        if len(span) >= 3 and detect_replay_or_slowmo(span):
            for f in span:
                f["replay_candidate"] = True
        i = j

    # Now classify and build segments.
    valid_keys: set[str] = set()
    ignored_segments: list[Segment] = []
    valid_segments: list[Segment] = []

    def reason_from_ctx(ctx: GameplayContext) -> str:
        if ctx == "replay":
            return "replay_or_slow_motion"
        if ctx == "pause":
            return "pause"
        if ctx == "coach_or_spectator":
            return "coach_or_spectator_view"
        if ctx == "closeup":
            return "closeup"
        if ctx == "scoreboard":
            return "scoreboard"
        return "unknown"

    current_valid: Segment | None = None
    current_ignored: Segment | None = None
    current_ignored_reason: str | None = None

    for idx, tsf in enumerate(timestamp_frames):
        # Rebuild detections for this timestamp:
        k = _timestamp_key(float(tsf["timestamp_sec"]))
        dets = by_ts[k]["detections"]
        valid = is_valid_gameplay_frame(
            tsf, dets, match_type=match_type, target_track_ids=target_track_ids
        )
        ctx = classify_frame_context(tsf, dets)
        if valid:
            valid_keys.add(k)
            if current_valid is None:
                current_valid = Segment(
                    start_sec=float(tsf["timestamp_sec"]),
                    end_sec=float(tsf["timestamp_sec"]),
                )
            else:
                current_valid.end_sec = float(tsf["timestamp_sec"])

            # flush ignored if switching
            if current_ignored is not None:
                ignored_segments.append(current_ignored)
                current_ignored = None
                current_ignored_reason = None
        else:
            r = reason_from_ctx(ctx)
            if current_valid is not None:
                # Finish valid segment
                if current_valid.end_sec - current_valid.start_sec >= 2.0:
                    valid_segments.append(current_valid)
                current_valid = None
            if current_ignored is None or r != current_ignored_reason:
                if current_ignored is not None:
                    ignored_segments.append(current_ignored)
                current_ignored_reason = r
                current_ignored = Segment(
                    start_sec=float(tsf["timestamp_sec"]),
                    end_sec=float(tsf["timestamp_sec"]),
                    reason=r,
                )
            else:
                current_ignored.end_sec = float(tsf["timestamp_sec"])

    # flush last
    if current_valid is not None:
        if current_valid.end_sec - current_valid.start_sec >= 2.0:
            valid_segments.append(current_valid)
    if current_ignored is not None:
        ignored_segments.append(current_ignored)

    total = max(1, len(timestamp_frames))
    ratio = len(valid_keys) / total
    warning = None
    if ratio < 0.45:
        warning = "Недостаточно игровых моментов для точного анализа."

    precision_proxy = 0.75 + 0.25 * ratio
    analysis_confidence = max(0.0, min(1.0, precision_proxy))

    return {
        "valid_segments": [{"start": s.start, "end": s.end} for s in valid_segments],
        "ignored_segments": [
            {"start": s.start, "end": s.end, "reason": (s.reason or "unknown")}
            for s in ignored_segments
        ],
        "valid_gameplay_ratio": round(ratio, 3),
        "warning": warning,
        "analysis_confidence": round(analysis_confidence, 3),
        "valid_timestamp_keys": sorted(valid_keys, key=lambda x: float(x)),
    }


def _court_visible_ratio(width: int, height: int, dets: list[Detection]) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    if not dets:
        return 0.0
    in_count = 0
    for d in dets:
        bbox = d.get("bbox")
        if not bbox:
            continue
        cx, cy = _bbox_center(bbox)
        x_ok = (cx / width) >= COURT_X_MIN and (cx / width) <= COURT_X_MAX
        y_ok = (cy / height) >= COURT_Y_MIN and (cy / height) <= COURT_Y_MAX
        if x_ok and y_ok:
            in_count += 1
    return in_count / len(dets)


def _avg_bbox_area_ratio(width: int, height: int, dets: list[Detection]) -> float:
    if width <= 0 or height <= 0:
        return 0.0
    if not dets:
        return 0.0
    total_area = width * height
    ratios: list[float] = []
    for d in dets:
        bbox = d.get("bbox")
        if not bbox:
            continue
        area = _bbox_area(bbox)
        ratios.append(area / total_area)
    if not ratios:
        return 0.0
    return float(sum(ratios) / len(ratios))


def _keypoints_ok_ratio(dets: list[Detection]) -> float:
    if not dets:
        return 0.0
    ok = 0
    for d in dets:
        if _keypoints_pose_ok(d.get("keypoints")):
            ok += 1
    return ok / len(dets)

