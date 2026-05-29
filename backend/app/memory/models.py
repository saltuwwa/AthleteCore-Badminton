"""SQLAlchemy models for turns and long-term memories (AthleteCore LTM)."""

from __future__ import annotations

import datetime as dt
import enum
import uuid
from typing import Any

from sqlalchemy import Boolean, Date, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ExtractedMemoryType(str, enum.Enum):
    fact = "fact"
    preference = "preference"
    opinion = "opinion"
    event = "event"


class MemoryLayer(str, enum.Enum):
    semantic = "semantic"
    episodic = "episodic"
    procedural = "procedural"


class RiskLevel(str, enum.Enum):
    low = "low"
    med = "med"
    high = "high"


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    session_id: Mapped[str] = mapped_column(String(512), index=True)
    user_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    messages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    turn_timestamp: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    memories: Mapped[list["Memory"]] = relationship(back_populates="turn")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    source_session: Mapped[str] = mapped_column(String(512), index=True)
    source_turn_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("turns.id", ondelete="CASCADE"), index=True
    )

    memory_type: Mapped[ExtractedMemoryType] = mapped_column(
        Enum(ExtractedMemoryType, name="extracted_memory_type_enum"), nullable=False
    )
    memory_layer: Mapped[MemoryLayer] = mapped_column(
        Enum(MemoryLayer, name="memory_layer_enum"), nullable=False, index=True
    )

    key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.9)
    importance: Mapped[float] = mapped_column(Float, default=0.5)

    event_type: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    risk_level: Mapped[RiskLevel | None] = mapped_column(
        Enum(RiskLevel, name="risk_level_enum"), nullable=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    # Structured sport event fields (schema v1+)
    event_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True, index=True)
    event_date_end: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    raw_user_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    sport: Mapped[str | None] = mapped_column(String(64), nullable=True, default="badminton")
    session_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    facts: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)

    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("memories.id", ondelete="SET NULL"), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    turn: Mapped["Turn"] = relationship(back_populates="memories")

    __table_args__ = (
        Index("ix_memories_user_active", "user_id", "active"),
        Index("ix_memories_user_event_date", "user_id", "event_date"),
        Index("ix_memories_user_session_type", "user_id", "session_type"),
    )
