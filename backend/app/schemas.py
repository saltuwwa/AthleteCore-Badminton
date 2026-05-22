from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class TurnMessage(BaseModel):
    role: Literal["user", "assistant", "tool"]
    content: str
    name: str | None = None


class TurnIn(BaseModel):
    session_id: str
    user_id: str | None = None
    messages: list[TurnMessage]
    timestamp: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class TurnCreated(BaseModel):
    id: str
    memories_written: int = 0


class RecallIn(BaseModel):
    query: str
    session_id: str
    user_id: str | None = None
    max_tokens: int = 1024


class Citation(BaseModel):
    turn_id: str
    score: float
    snippet: str
    memory_layer: str | None = None


class RecallOut(BaseModel):
    context: str
    citations: list[Citation]


class SearchIn(BaseModel):
    query: str
    session_id: str | None = None
    user_id: str | None = None
    limit: int = 10


class SearchResultItem(BaseModel):
    content: str
    score: float
    session_id: str
    timestamp: datetime
    metadata: dict[str, Any]
    user_id: str | None = None
    memory_layer: str | None = None


class SearchOut(BaseModel):
    results: list[SearchResultItem]


class MemoryOut(BaseModel):
    id: str
    user_id: str | None = None
    type: Literal["fact", "preference", "opinion", "event"]
    layer: Literal["semantic", "episodic", "procedural"]
    key: str
    value: str
    confidence: float
    importance: float
    event_type: str | None = None
    risk_level: str | None = None
    source_session: str
    source_turn: str
    created_at: datetime
    updated_at: datetime
    supersedes: str | None
    active: bool


class MemoriesListOut(BaseModel):
    memories: list[MemoryOut]


class TranscribeResponse(BaseModel):
    text: str
    duration_sec: float | None = None
    language: str = "ru"


class ChatResponse(BaseModel):
    message: str
    thread_id: str
    agents_used: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    analysis: dict[str, Any] | None = None
    needs_memory: bool = False
    memory_citations_count: int = 0
