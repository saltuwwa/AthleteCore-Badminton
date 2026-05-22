from app.graph.llm import heuristic_route, parse_planner_json


def test_heuristic_analyst_ru():
    d = heuristic_route("После матча снова ошибка на подаче в третьем сете")
    assert d["agents"] == ["analyst"]


def test_heuristic_health():
    d = heuristic_route("Очень устала, как восстановиться после недели?")
    assert d["agents"] == ["health_coach"]


def test_parse_planner_json():
    raw = '{"agents": ["scheduler"], "reason": "plan", "needs_confirmation": true}'
    d = parse_planner_json(raw)
    assert d["agents"] == ["scheduler"]
