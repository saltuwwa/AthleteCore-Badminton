"""Calendar CRUD used by MCP tools, LangGraph Scheduler, and REST API."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import ScheduleEvent, ScheduleEventStatus
from .seed import SEED_EVENTS


class ScheduleService:
    async def ensure_seeded(self, session: AsyncSession, user_id: str = "aigerim") -> None:
        existing = await session.scalar(
            select(ScheduleEvent.id).where(ScheduleEvent.user_id == user_id).limit(1)
        )
        if existing:
            return
        for row in SEED_EVENTS:
            session.add(ScheduleEvent(user_id=user_id, **row))
        await session.flush()

    async def list_events(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        include_pending: bool = True,
    ) -> list[ScheduleEvent]:
        await self.ensure_seeded(session, user_id)
        q = select(ScheduleEvent).where(ScheduleEvent.user_id == user_id)
        if date_from:
            q = q.where(ScheduleEvent.event_date >= date_from)
        if date_to:
            q = q.where(ScheduleEvent.event_date <= date_to)
        if not include_pending:
            q = q.where(ScheduleEvent.status == ScheduleEventStatus.confirmed.value)
        q = q.order_by(ScheduleEvent.event_date, ScheduleEvent.start_time)
        return list((await session.scalars(q)).all())

    async def propose_block(
        self,
        session: AsyncSession,
        *,
        user_id: str,
        event_date: str,
        start_time: str,
        end_time: str,
        title: str,
        event_type: str = "TRAINING",
        intensity: int | None = 3,
        notes: str | None = None,
    ) -> ScheduleEvent:
        await self.ensure_seeded(session, user_id)
        event = ScheduleEvent(
            user_id=user_id,
            event_date=event_date,
            start_time=start_time,
            end_time=end_time,
            title=title,
            event_type=event_type.upper(),
            intensity=intensity,
            ai_added=True,
            status=ScheduleEventStatus.pending_confirmation.value,
            notes=notes,
        )
        session.add(event)
        await session.flush()
        return event

    def default_week_range(self) -> tuple[str, str]:
        today = date.today()
        return today.isoformat(), (today + timedelta(days=14)).isoformat()
