"""Schedule tools for MCP + Scheduler agent."""

from __future__ import annotations

from app.database import AsyncSessionLocal
from app.schedule.service import ScheduleService

_schedule = ScheduleService()


async def get_training_schedule(
    *,
    user_id: str = "aigerim",
    date_from: str | None = None,
    date_to: str | None = None,
    include_pending: bool = True,
) -> dict:
    """List calendar blocks in ISO date range (defaults: today → +14 days)."""
    if not date_from or not date_to:
        date_from, date_to = _schedule.default_week_range()

    async with AsyncSessionLocal() as session:
        rows = await _schedule.list_events(
            session,
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
            include_pending=include_pending,
        )
        await session.commit()

    events = [
        {
            "id": e.id,
            "date": e.event_date,
            "start": e.start_time,
            "end": e.end_time,
            "title": e.title,
            "type": e.event_type,
            "intensity": e.intensity,
            "ai_added": e.ai_added,
            "status": e.status,
            "notes": e.notes,
        }
        for e in rows
    ]
    return {
        "user_id": user_id,
        "date_from": date_from,
        "date_to": date_to,
        "count": len(events),
        "events": events,
    }


async def propose_training_block(
    *,
    user_id: str = "aigerim",
    title: str,
    event_date: str,
    start_time: str,
    end_time: str,
    event_type: str = "TRAINING",
    intensity: int = 3,
    reason: str | None = None,
) -> dict:
    """
    Propose a new block (status=pending_confirmation). Athlete must confirm in UI.

    Does not overwrite existing events — check get_training_schedule first.
    """
    async with AsyncSessionLocal() as session:
        event = await _schedule.propose_block(
            session,
            user_id=user_id,
            event_date=event_date,
            start_time=start_time,
            end_time=end_time,
            title=title,
            event_type=event_type,
            intensity=intensity,
            notes=reason,
        )
        await session.commit()

    return {
        "id": event.id,
        "status": event.status,
        "message": (
            f"Предложен блок «{title}» на {event_date} {start_time}–{end_time}. "
            "Требуется подтверждение спортсмена (HITL)."
        ),
        "event": {
            "date": event.event_date,
            "start": event.start_time,
            "end": event.end_time,
            "title": event.title,
            "type": event.event_type,
            "intensity": event.intensity,
        },
    }


def format_schedule_context(payload: dict) -> str:
    lines = [
        f"## Calendar {payload['date_from']} → {payload['date_to']} ({payload['count']} events)"
    ]
    for e in payload.get("events", [])[:20]:
        pending = " [PENDING]" if e.get("status") == "pending_confirmation" else ""
        inten = f", load {e['intensity']}/5" if e.get("intensity") else ""
        lines.append(
            f"- {e['date']} {e['start']}–{e['end']}: {e['title']} ({e['type']}{inten}){pending}"
        )
    return "\n".join(lines)
