"""Default calendar aligned with frontend demo (scheduleData.ts)."""

from __future__ import annotations

from datetime import date, timedelta

SEED_EVENTS: list[dict] = []


def _build_seed() -> list[dict]:
    today = date.today()
    events: list[dict] = []

    def d(offset: int) -> str:
        return (today + timedelta(days=offset)).isoformat()

    raw = [
        (-2, "08:00", "09:30", "Кардио + разминка", "TRAINING", 2, False),
        (-1, "11:00", "12:30", "Скоростная работа", "TRAINING", 4, False),
        (-1, "18:00", "19:00", "Видеоразбор сетки", "STUDY", None, False),
        (0, "09:00", "10:30", "Технический блок", "TRAINING", 3, True),
        (0, "14:00", "15:00", "Восстановление / бассейн", "RECOVERY", None, False),
        (0, "19:30", "20:30", "ОФП в зале", "GYM", 3, False),
        (1, "10:00", "12:00", "Спарринг с тренером", "TRAINING", 5, False),
        (2, "17:00", "20:00", "Турнир Almaty Open · 1/16", "MATCH", 5, False),
        (3, "09:00", "10:00", "Лёгкий бег", "RECOVERY", None, True),
        (3, "15:00", "16:30", "Тактический разбор", "STUDY", None, False),
        (4, "11:00", "13:00", "Реакция и работа ног", "TRAINING", 4, True),
        (5, "18:00", "19:30", "Командная игра", "TRAINING", 3, False),
        (7, "10:00", "11:30", "Силовая (нижний день)", "GYM", 4, False),
        (9, "17:00", "20:00", "Almaty Open · 1/8", "MATCH", 5, False),
        (12, "08:30", "09:30", "Йога + растяжка", "RECOVERY", None, False),
        (14, "11:00", "13:00", "Контрольная сессия", "TRAINING", 4, False),
        (18, "15:00", "17:00", "Подготовка к этапу", "TRAINING", 3, False),
        (21, "09:00", "12:00", "BWF Regional · группа", "MATCH", 5, False),
    ]
    for day_off, start, end, title, etype, intensity, ai_added in raw:
        events.append(
            {
                "event_date": d(day_off),
                "start_time": start,
                "end_time": end,
                "title": title,
                "event_type": etype,
                "intensity": intensity,
                "ai_added": ai_added,
                "status": "confirmed",
            }
        )
    return events


SEED_EVENTS = _build_seed()
