from __future__ import annotations

import json
import re
from typing import Any

from fastapi import HTTPException

from app.document_analysis.config import doc_settings
from app.document_analysis.schemas import DocumentAction, StructuredCompetitionData
from app.security.untrusted_content import (
    GEMINI_UNTRUSTED_SYSTEM_ADDENDUM,
    build_safe_gemini_user_blob,
)


_ACTION_INSTRUCTIONS: dict[DocumentAction, str] = {
    "parse_results": "Разбери турнирные результаты из данных документа. Кратко: таблица, ключевые матчи, итог.",
    "find_my_matches": "Найди матчи указанного атлета в документе. Перечисли соперников и счёт.",
    "compare_past": "Сравни этот турнир с типичными прошлыми результатами (если есть контекст). Отметь прогресс или регресс.",
}


def analyze_document_safe(
    *,
    action: DocumentAction,
    structured: StructuredCompetitionData,
    safe_excerpt: str,
    athlete_name: str | None = None,
    memory_context: str = "",
) -> tuple[StructuredCompetitionData, str]:
    if not doc_settings.google_api_key:
        msg = _fallback_message(structured, action)
        return structured, msg

    user_inst = _ACTION_INSTRUCTIONS[action]
    if athlete_name:
        user_inst += f"\nAthlete name to focus: {athlete_name}"

    blob = build_safe_gemini_user_blob(
        user_instruction=user_inst + ("\n\n" + memory_context if memory_context else ""),
        untrusted_excerpt=safe_excerpt[:20_000],
        structured_json=structured.model_dump_json(),
    )

    try:
        import google.generativeai as genai
    except ImportError as e:
        raise HTTPException(status_code=503, detail="google-generativeai required") from e

    genai.configure(api_key=doc_settings.google_api_key)
    model = genai.GenerativeModel(
        doc_settings.document_gemini_model,
        system_instruction=(
            "You are AthleteCore competition document analyst. "
            "Respond in Russian. Return JSON with keys: "
            "assistant_message (string), structured (object with tournament fields). "
            + GEMINI_UNTRUSTED_SYSTEM_ADDENDUM
        ),
    )
    resp = model.generate_content(
        blob,
        generation_config={"temperature": 0.25, "response_mime_type": "application/json"},
    )
    raw = (resp.text or "").strip()
    data = _parse_json(raw)
    msg = str(data.get("assistant_message", "")).strip() or _fallback_message(structured, action)
    st = data.get("structured")
    if isinstance(st, dict):
        from app.document_analysis.entity_parser import merge_gemini_structured

        structured = merge_gemini_structured(structured, st)
    return structured, msg


def _parse_json(text: str) -> dict[str, Any]:
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        return {"assistant_message": text}


def _fallback_message(structured: StructuredCompetitionData, action: DocumentAction) -> str:
    n = len(structured.match_list)
    t = structured.tournament_name or "Турнир"
    base = f"{t}: найдено матчей ~{n}."
    if structured.security_notice:
        base = structured.security_notice + " " + base
    if action == "find_my_matches":
        base += " Укажи имя в запросе для точного фильтра."
    return base
