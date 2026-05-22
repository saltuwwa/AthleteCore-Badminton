from app.graph.llm import extract_analysis_json, strip_analysis_json_from_text


def test_strip_analysis_json_removes_fenced_block():
    raw = """Текст анализа.

```json
{"errors":[{"tag":"HIGH","category":"technical","description":"Ошибка","fix":"Фикс"}],"pattern_note":"Паттерн"}
```
"""
    analysis = extract_analysis_json(raw)
    cleaned = strip_analysis_json_from_text(raw)
    assert analysis is not None
    assert "errors" not in cleaned
    assert "```json" not in cleaned
    assert cleaned.startswith("Текст анализа")
