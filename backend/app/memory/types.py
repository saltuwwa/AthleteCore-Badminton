from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class MemoryType(str, Enum):
    SEMANTIC = "semantic"
    EPISODIC = "episodic"
    PROCEDURAL = "procedural"


class RiskLevel(str, Enum):
    LOW = "low"
    MED = "med"
    HIGH = "high"


@dataclass(slots=True)
class BaseMemory:
    id: str
    user_id: str
    memory_type: MemoryType
    created_at: datetime
    updated_at: datetime
    importance: float = 0.5
    confidence: float = 0.7
    source_event_id: str | None = None
    tags: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SemanticMemory(BaseMemory):
    fact_key: str = ""
    value: str = ""
    valid_from: datetime | None = None
    valid_to: datetime | None = None


@dataclass(slots=True)
class EpisodicMemory(BaseMemory):
    event_type: str = ""
    timestamp: datetime | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LOW


@dataclass(slots=True)
class ProceduralMemory(BaseMemory):
    rule_key: str = ""
    rule_value: str = ""
    reason: str = ""


@dataclass(slots=True)
class RetrievedMemory:
    memory: BaseMemory
    relevance: float
    recency: float
    importance: float
    final_score: float
