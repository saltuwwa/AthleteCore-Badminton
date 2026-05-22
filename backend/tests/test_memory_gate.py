from app.graph.memory_gate import heuristic_needs_memory, resolve_needs_memory


def test_skip_weather():
    assert not heuristic_needs_memory("Какая погода в Алматы завтра?", "direct")


def test_skip_calendar_move():
    assert not heuristic_needs_memory(
        "Перенеси тренировку с 18:00 на 19:00 в четверг", "scheduler"
    )


def test_memory_weekly_plan():
    assert heuristic_needs_memory(
        "Составь расписание на неделю с учётом моей нагрузки", "scheduler"
    )


def test_memory_match_analysis():
    assert heuristic_needs_memory(
        "После матча снова ошибка на подаче в третьем сете", "analyst"
    )


def test_resolve_forces_skip_off_topic():
    assert not resolve_needs_memory(
        "Какая погода?",
        "direct",
        {"needs_memory": True},
    )
