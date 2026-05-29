"""Run repeated /api/chat latency benchmarks for key scenarios."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import uuid
from dataclasses import dataclass
from typing import Any

import httpx


SCENARIOS: list[tuple[str, str]] = [
    ("GENERAL_CHAT", "как дела?"),
    ("NEW_EVENT_LOG", "вчера была тренировка: бег 5 км, многоваланка, подвернула голеностоп"),
    ("PAST_EVENT_LOOKUP_found", "разбери мою тренировку которая была 28го мая"),
    ("PAST_EVENT_LOOKUP_not_found", "разбери мою тренировку 10го февраля"),
    ("ADVICE_REQUEST", "как восстановиться после того, как подвернула голеностоп?"),
]


@dataclass
class RunRecord:
    scenario: str
    status_code: int
    total_ms: float | None
    semantic_router_ms: float | None
    agent_llm_ms: float | None
    memory_write_ms: float | None
    methodology_rag_ms: float | None
    route_source: str | None
    memory_write_mode: str | None
    memory_write_scheduled: bool | None
    methodology_rag_skipped_reason: str | None
    llm_calls: list[dict[str, Any]]
    error: str | None


def _p95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    rank = math.ceil(0.95 * len(ordered)) - 1
    rank = max(0, min(rank, len(ordered) - 1))
    return ordered[rank]


def _summary(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min_ms": None, "median_ms": None, "avg_ms": None, "p95_ms": None, "max_ms": None}
    return {
        "min_ms": min(values),
        "median_ms": statistics.median(values),
        "avg_ms": statistics.fmean(values),
        "p95_ms": _p95(values),
        "max_ms": max(values),
    }


async def _one_call(client: httpx.AsyncClient, base_url: str, message: str, user_id: str, session_id: str) -> RunRecord:
    payload = {
        "message": message,
        "user_id": user_id,
        "session_id": session_id,
        "thread_id": str(uuid.uuid4()),
    }
    try:
        resp = await client.post(f"{base_url}/api/chat", data=payload)
        data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return RunRecord(
            scenario="",
            status_code=0,
            total_ms=None,
            semantic_router_ms=None,
            agent_llm_ms=None,
            memory_write_ms=None,
            methodology_rag_ms=None,
            route_source=None,
            memory_write_mode=None,
            memory_write_scheduled=None,
            methodology_rag_skipped_reason=None,
            llm_calls=[],
            error=f"{type(exc).__name__}: {exc!s}",
        )

    lt = (data.get("latency_trace") or {}) if isinstance(data, dict) else {}
    stages = lt.get("stages") or {}
    return RunRecord(
        scenario="",
        status_code=resp.status_code,
        total_ms=lt.get("total_ms"),
        semantic_router_ms=stages.get("semantic_router_ms"),
        agent_llm_ms=stages.get("agent_llm_ms"),
        memory_write_ms=stages.get("memory_write_ms"),
        methodology_rag_ms=stages.get("methodology_rag_ms"),
        route_source=lt.get("route_source"),
        memory_write_mode=lt.get("memory_write_mode"),
        memory_write_scheduled=lt.get("memory_write_scheduled"),
        methodology_rag_skipped_reason=lt.get("methodology_rag_skipped_reason"),
        llm_calls=lt.get("llm_calls") or [],
        error=None if resp.status_code == 200 else json.dumps(data, ensure_ascii=False),
    )


def _median_from_records(records: list[RunRecord], field: str) -> float | None:
    vals = [getattr(r, field) for r in records if isinstance(getattr(r, field), (int, float))]
    return statistics.median(vals) if vals else None


def _cache_stats(records: list[RunRecord]) -> dict[str, Any]:
    route_sources = [r.route_source for r in records if r.route_source]
    router_cache_hits = sum(1 for s in route_sources if s == "semantic_router_cache")
    return {
        "router_cache_hit_count": router_cache_hits,
        "router_cache_miss_count": max(0, len(records) - router_cache_hits),
        "route_source_counts": {s: route_sources.count(s) for s in sorted(set(route_sources))},
    }


async def run_benchmark(base_url: str, repeats: int, user_id: str, session_id: str, timeout_s: float) -> dict[str, Any]:
    out: dict[str, Any] = {"config": {"base_url": base_url, "repeats": repeats, "user_id": user_id, "session_id": session_id}}
    results: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        await client.get(f"{base_url}/docs")
        for scenario_name, scenario_message in SCENARIOS:
            recs: list[RunRecord] = []
            for _ in range(repeats):
                rec = await _one_call(client, base_url, scenario_message, user_id, session_id)
                rec.scenario = scenario_name
                recs.append(rec)

            ok = [r for r in recs if r.status_code == 200 and r.error is None and r.total_ms is not None]
            totals = [float(r.total_ms) for r in ok if r.total_ms is not None]
            results[scenario_name] = {
                "samples": len(ok),
                "errors": [r.error for r in recs if r.error],
                **_summary(totals),
                "semantic_router_median_ms": _median_from_records(ok, "semantic_router_ms"),
                "agent_llm_median_ms": _median_from_records(ok, "agent_llm_ms"),
                "memory_write_median_ms": _median_from_records(ok, "memory_write_ms"),
                "methodology_rag_median_ms": _median_from_records(ok, "methodology_rag_ms"),
                "route_source": sorted({r.route_source for r in ok if r.route_source}),
                "memory_write_mode": sorted({r.memory_write_mode for r in ok if r.memory_write_mode}),
                "memory_write_scheduled_any": any(bool(r.memory_write_scheduled) for r in ok),
                "methodology_rag_skipped_reasons": sorted(
                    {r.methodology_rag_skipped_reason for r in ok if r.methodology_rag_skipped_reason}
                ),
                "cache": _cache_stats(ok),
                "raw_runs": [
                    {
                        "total_ms": r.total_ms,
                        "semantic_router_ms": r.semantic_router_ms,
                        "agent_llm_ms": r.agent_llm_ms,
                        "memory_write_ms": r.memory_write_ms,
                        "methodology_rag_ms": r.methodology_rag_ms,
                        "route_source": r.route_source,
                        "memory_write_mode": r.memory_write_mode,
                        "memory_write_scheduled": r.memory_write_scheduled,
                        "methodology_rag_skipped_reason": r.methodology_rag_skipped_reason,
                    }
                    for r in ok
                ],
            }
    out["scenarios"] = results
    return out


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Repeated /api/chat latency benchmark")
    p.add_argument("--base-url", default="http://127.0.0.1:8001")
    p.add_argument("--repeats", type=int, default=5)
    p.add_argument("--user-id", default="aigerim")
    p.add_argument("--session-id", default="main")
    p.add_argument("--timeout-sec", type=float, default=180.0)
    p.add_argument("--out", default="", help="Optional output JSON path")
    return p


async def _main() -> None:
    args = _build_parser().parse_args()
    report = await run_benchmark(
        base_url=args.base_url,
        repeats=max(5, args.repeats),
        user_id=args.user_id,
        session_id=args.session_id,
        timeout_s=args.timeout_sec,
    )
    blob = json.dumps(report, ensure_ascii=False, indent=2)
    print(blob)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(blob)


if __name__ == "__main__":
    import asyncio

    asyncio.run(_main())
