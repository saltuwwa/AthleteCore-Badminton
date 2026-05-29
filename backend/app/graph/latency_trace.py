"""Per-request latency profiling for /api/chat (development_mode)."""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

from app.config import settings

logger = logging.getLogger(__name__)

_current: ContextVar["LatencyTrace | None"] = ContextVar("latency_trace", default=None)

STAGE_KEYS = (
    "semantic_router_ms",
    "date_normalizer_ms",
    "structured_retrieval_ms",
    "memory_recall_ms",
    "methodology_rag_ms",
    "turn_safety_ms",
    "agent_llm_ms",
    "response_parsing_ms",
    "memory_write_ms",
    "response_assembly_ms",
    "graph_invoke_ms",
)


@dataclass
class LlmCallRecord:
    name: str
    model: str
    duration_ms: float
    prompt_chars: int
    completion_chars: int


@dataclass
class DbCallRecord:
    name: str
    duration_ms: float
    rows: int = 0


@dataclass
class LatencyTrace:
    request_id: str
    _t0: float = field(default_factory=time.perf_counter)
    _finished: bool = False
    stages_ms: dict[str, float] = field(default_factory=dict)
    llm_calls: list[LlmCallRecord] = field(default_factory=list)
    db_calls: list[DbCallRecord] = field(default_factory=list)
    markers: dict[str, float] = field(default_factory=dict)
    meta: dict[str, Any] = field(default_factory=dict)

    def set_meta(self, key: str, value: Any) -> None:
        self.meta[key] = value

    def mark(self, name: str) -> None:
        self.markers[name] = time.perf_counter()

    def add_stage_ms(self, stage: str, duration_ms: float) -> None:
        key = stage if stage.endswith("_ms") else f"{stage}_ms"
        self.stages_ms[key] = self.stages_ms.get(key, 0.0) + duration_ms

    def record_llm_call(
        self,
        *,
        name: str,
        model: str,
        duration_ms: float,
        prompt_chars: int,
        completion_chars: int,
    ) -> None:
        self.llm_calls.append(
            LlmCallRecord(
                name=name,
                model=model,
                duration_ms=round(duration_ms, 2),
                prompt_chars=prompt_chars,
                completion_chars=completion_chars,
            )
        )

    def record_db_call(self, *, name: str, duration_ms: float, rows: int = 0) -> None:
        self.db_calls.append(
            DbCallRecord(
                name=name,
                duration_ms=round(duration_ms, 2),
                rows=rows,
            )
        )

    @property
    def total_ms(self) -> float:
        return round((time.perf_counter() - self._t0) * 1000, 2)

    def finish(self) -> None:
        if not self._finished:
            self.markers["api_response_ready"] = time.perf_counter()
            self._finished = True

    def to_dict(self) -> dict[str, Any]:
        stages = {k: 0.0 for k in STAGE_KEYS}
        stages.update({k: round(v, 2) for k, v in self.stages_ms.items()})
        payload: dict[str, Any] = {
            "request_id": self.request_id,
            "total_ms": self.total_ms,
            "stages": stages,
            "llm_calls": [
                {
                    "name": c.name,
                    "model": c.model,
                    "duration_ms": c.duration_ms,
                    "prompt_chars": c.prompt_chars,
                    "completion_chars": c.completion_chars,
                }
                for c in self.llm_calls
            ],
            "db_calls": [
                {
                    "name": c.name,
                    "duration_ms": c.duration_ms,
                    "rows": c.rows,
                }
                for c in self.db_calls
            ],
        }
        if self.meta:
            payload.update(self.meta)
        return payload


def init_latency_trace(request_id: str | None = None) -> LatencyTrace:
    trace = LatencyTrace(request_id=request_id or str(uuid.uuid4()))
    _current.set(trace)
    trace.mark("request_received")
    return trace


def current_latency_trace() -> LatencyTrace | None:
    return _current.get()


def clear_latency_trace() -> None:
    _current.set(None)


@contextmanager
def stage_span(stage: str) -> Iterator[None]:
    """Accumulate wall time into stages_ms[stage_ms] and Langfuse observation spans."""
    from app.observability.langfuse_tracing import langfuse_observation_span

    trace = current_latency_trace()
    lf_name = stage[:-3] if stage.endswith("_ms") else stage

    with langfuse_observation_span(lf_name):
        if trace is None:
            yield
            return
        t0 = time.perf_counter()
        try:
            yield
        finally:
            trace.add_stage_ms(stage, (time.perf_counter() - t0) * 1000)


def log_latency_summary(trace: LatencyTrace) -> None:
    if not settings.development_mode:
        return
    d = trace.to_dict()
    s = d["stages"]
    parts = [
        f"[latency] request_id={trace.request_id} total={d['total_ms']:.0f}ms",
        f"  semantic_router={s.get('semantic_router_ms', 0):.0f}ms",
        f"  date_normalizer={s.get('date_normalizer_ms', 0):.0f}ms",
        f"  structured_retrieval={s.get('structured_retrieval_ms', 0):.0f}ms",
        f"  memory_recall={s.get('memory_recall_ms', 0):.0f}ms",
        f"  methodology_rag={s.get('methodology_rag_ms', 0):.0f}ms",
        f"  turn_safety={s.get('turn_safety_ms', 0):.0f}ms",
        f"  agent_llm={s.get('agent_llm_ms', 0):.0f}ms",
        f"  response_parsing={s.get('response_parsing_ms', 0):.0f}ms",
        f"  memory_write={s.get('memory_write_ms', 0):.0f}ms",
        f"  response_assembly={s.get('response_assembly_ms', 0):.0f}ms",
        f"  graph_invoke={s.get('graph_invoke_ms', 0):.0f}ms",
    ]
    for call in d.get("llm_calls") or []:
        parts.append(
            f"  llm {call['name']}: {call['model']} {call['duration_ms']:.0f}ms "
            f"(prompt={call['prompt_chars']} completion={call['completion_chars']})"
        )
    for db in d.get("db_calls") or []:
        parts.append(
            f"  db {db['name']}: {db['duration_ms']:.0f}ms rows={db['rows']}"
        )
    logger.info("\n".join(parts))
    print("\n".join(parts), flush=True)
