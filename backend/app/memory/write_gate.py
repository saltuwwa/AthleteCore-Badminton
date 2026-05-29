from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .constants import (
    SOURCE_ASSISTANT,
    SOURCE_CONFIRMED_ANALYSIS,
    WRITABLE_SOURCES,
)
from .mapping import parse_risk_level
from .memory_classification import (
    FACT_PENDING_UNRESOLVED_DATE,
    MIN_EPISODIC_DATE_CONFIDENCE,
    SportMemoryCategory,
    classify_sport_memory,
    detect_noise_intent,
    event_date_confidence,
    has_episodic_substance,
    is_analysis_only_request,
    is_procedural_disallowed,
)
from .models import RiskLevel

EPISODIC_DATE_REQUIRED = frozenset(
    {
        SportMemoryCategory.MATCH_LOG,
        SportMemoryCategory.TRAINING_LOG,
    }
)


@dataclass(slots=True)
class WriteDecision:
    allow: bool
    reason: str
    pending_unresolved_date: bool = False


class MemoryWriteGate:
    """
    Allow only structured sport-memory categories.

    Episodic match/training logs need a resolved event_date (confidence ≥ threshold)
    or are stored with pending_unresolved_date (excluded from SQL «last event» lookups).
    """

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
        source: str | None = None,
        event_date: Any = None,
        memory_layer: str | None = None,
        facts: dict[str, Any] | None = None,
        value: str | None = None,
        raw_user_text: str | None = None,
        candidate: dict[str, Any] | None = None,
    ) -> WriteDecision:
        if is_small_talk:
            return WriteDecision(False, "small-talk")

        noise = detect_noise_intent(raw_user_text)
        if noise:
            return WriteDecision(False, noise)

        src = (source or "user").lower()
        if src == SOURCE_ASSISTANT:
            return WriteDecision(False, "assistant-source-blocked")
        if src == SOURCE_CONFIRMED_ANALYSIS and not is_user_confirmed:
            return WriteDecision(False, "confirmed-analysis-requires-user-confirmation")
        if src not in WRITABLE_SOURCES:
            return WriteDecision(False, f"source-not-writable:{src}")

        cand = candidate or {
            "key": fact_key,
            "value": value,
            "event_type": event_type,
            "source": source,
            "memory_layer": memory_layer,
            "type": memory_type,
            "facts": facts or {},
            "event_date": event_date,
            "is_repeated_pattern": is_repeated_pattern,
            "is_user_confirmed": is_user_confirmed,
            "risk_level": risk_level.value if risk_level else None,
        }

        if is_procedural_disallowed(cand):
            return WriteDecision(False, "procedural-or-calendar-not-allowed")

        category = classify_sport_memory(cand)
        if category is None:
            return WriteDecision(False, "category-not-allowed")

        if category == SportMemoryCategory.CONFIRMED_COACH_FEEDBACK:
            if not is_user_confirmed:
                return WriteDecision(False, "coach-feedback-not-confirmed")
            return WriteDecision(True, "confirmed-coach-feedback")

        if category == SportMemoryCategory.RECURRING_WEAKNESS:
            if not (is_repeated_pattern or risk_level in {RiskLevel.med, RiskLevel.high}):
                return WriteDecision(False, "weakness-not-recurring")
            return WriteDecision(True, "recurring-weakness")

        if category in EPISODIC_DATE_REQUIRED:
            return self._episodic_date_policy(
                cand,
                event_date=event_date,
                raw_user_text=raw_user_text,
            )

        # Goals, health, recovery, pipelines — no calendar date required
        if category in {
            SportMemoryCategory.GOAL,
            SportMemoryCategory.HEALTH_LOG,
            SportMemoryCategory.INJURY_NOTE,
            SportMemoryCategory.RECOVERY_LOG,
            SportMemoryCategory.VIDEO_ANALYSIS,
            SportMemoryCategory.COMPETITION_DOCUMENT_ANALYSIS,
            SportMemoryCategory.TOURNAMENT_RESULT,
        }:
            return WriteDecision(True, f"allowed:{category.value}")

        return WriteDecision(False, "category-not-allowed")

    def _episodic_date_policy(
        self,
        candidate: dict[str, Any],
        *,
        event_date: Any,
        raw_user_text: str | None,
    ) -> WriteDecision:
        if is_analysis_only_request(raw_user_text or "") and not has_episodic_substance(
            candidate
        ):
            return WriteDecision(False, "analysis-request-without-facts")

        conf = event_date_confidence(candidate)
        if event_date and conf >= MIN_EPISODIC_DATE_CONFIDENCE:
            return WriteDecision(True, "episodic-date-resolved")

        if event_date and conf > 0:
            return WriteDecision(True, "episodic-date-low-confidence", pending_unresolved_date=True)

        if has_episodic_substance(candidate):
            return WriteDecision(
                True,
                "pending-unresolved-date",
                pending_unresolved_date=True,
            )

        return WriteDecision(False, "episodic-missing-date-and-substance")

    def filter_candidates(
        self,
        candidates: list[dict[str, Any]],
        *,
        raw_user_text: str | None = None,
    ) -> list[dict[str, Any]]:
        kept: list[dict[str, Any]] = []
        for c in candidates:
            blob = (c.get("raw_user_text") or raw_user_text or "").strip() or None
            decision = self.should_write(
                event_type=c.get("event_type"),
                risk_level=parse_risk_level(c.get("risk_level")),
                is_user_confirmed=bool(c.get("is_user_confirmed")),
                is_repeated_pattern=bool(c.get("is_repeated_pattern")),
                fact_key=c.get("key"),
                memory_type=str(c.get("type", "fact")),
                source=c.get("source"),
                event_date=c.get("event_date"),
                memory_layer=c.get("memory_layer"),
                facts=c.get("facts") if isinstance(c.get("facts"), dict) else {},
                value=c.get("value"),
                raw_user_text=blob,
                candidate=c,
            )
            if not decision.allow:
                continue
            if decision.pending_unresolved_date:
                c = dict(c)
                c["event_date"] = None
                c["event_date_end"] = None
                facts = dict(c.get("facts") or {})
                facts[FACT_PENDING_UNRESOLVED_DATE] = True
                cat = classify_sport_memory(c)
                if cat:
                    facts.setdefault("sport_memory_category", cat.value)
                c["facts"] = facts
            kept.append(c)
        return kept
