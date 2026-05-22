from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .mapping import parse_risk_level
from .models import RiskLevel


@dataclass(slots=True)
class WriteDecision:
    allow: bool
    reason: str


class MemoryWriteGate:
    IMPORTANT_KEY_FRAGMENTS = (
        "goal.",
        "health.injury",
        "training.preference",
        "recovery.",
        "constraint.",
        "performance.error",
        "schedule.confirmation",
        "hitl.",
        "agent.",
    )

    def should_write(
        self,
        *,
        event_type: str | None = None,
        risk_level: RiskLevel | None = None,
        is_user_confirmed: bool = False,
        is_repeated_pattern: bool = False,
        fact_key: str | None = None,
        is_small_talk: bool = False,
        memory_type: str = "fact",
    ) -> WriteDecision:
        if is_small_talk:
            return WriteDecision(False, "small-talk")

        if is_user_confirmed:
            return WriteDecision(True, "hitl-confirmed")

        if is_repeated_pattern:
            return WriteDecision(True, "repeated-pattern")

        if risk_level in {RiskLevel.med, RiskLevel.high}:
            return WriteDecision(True, f"risk-{risk_level.value}")

        key = (fact_key or "").lower()
        if any(frag in key for frag in self.IMPORTANT_KEY_FRAGMENTS):
            return WriteDecision(True, f"important-key:{key}")

        if event_type in {"match_log", "training_log", "schedule_confirmation"}:
            return WriteDecision(True, "core-event")

        if memory_type == "event":
            return WriteDecision(True, "event-type")

        if memory_type in {"fact", "preference", "opinion"}:
            return WriteDecision(True, "durable-trait")

        return WriteDecision(False, "not-important-enough")

    def filter_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept: list[dict[str, Any]] = []
        for c in candidates:
            decision = self.should_write(
                event_type=c.get("event_type"),
                risk_level=parse_risk_level(c.get("risk_level")),
                is_user_confirmed=bool(c.get("is_user_confirmed")),
                is_repeated_pattern=bool(c.get("is_repeated_pattern")),
                fact_key=c.get("key"),
                memory_type=str(c.get("type", "fact")),
            )
            if decision.allow:
                kept.append(c)
        return kept
