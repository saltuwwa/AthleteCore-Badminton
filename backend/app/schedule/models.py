"""Training calendar persisted for Schedule Agent + MCP tools."""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.memory.models import Base


class ScheduleEventStatus(str, enum.Enum):
    confirmed = "confirmed"
    pending_confirmation = "pending_confirmation"


class ScheduleEvent(Base):
    __tablename__ = "schedule_events"

    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(128), index=True, default="aigerim")
    event_date: Mapped[str] = mapped_column(String(10), index=True)  # YYYY-MM-DD
    start_time: Mapped[str] = mapped_column(String(5))  # HH:MM
    end_time: Mapped[str] = mapped_column(String(5))
    title: Mapped[str] = mapped_column(String(256))
    event_type: Mapped[str] = mapped_column(String(32))  # TRAINING, RECOVERY, MATCH, ...
    intensity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ai_added: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(
        String(32), default=ScheduleEventStatus.confirmed.value, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
