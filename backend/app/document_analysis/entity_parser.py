from __future__ import annotations

import json
import re
from typing import Any

from app.document_analysis.schemas import MatchEntry, StructuredCompetitionData
from app.document_analysis.table_parser import parse_table_matches
from app.security.untrusted_content import InjectionScanResult

_SCORE_RE = re.compile(
    r"(\d{1,2})\s*[-:–]\s*(\d{1,2})",
)
_VS_RE = re.compile(
    r"([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\s\.\-]{2,40})\s+(?:vs|v\.|—|-|–)\s+([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\s\.\-]{2,40})",
    re.I,
)
_DATE_RE = re.compile(
    r"\b(20\d{2}[-/.]\d{1,2}[-/.]\d{1,2}|\d{1,2}[./]\d{1,2}[./]20\d{2})\b"
)
_ROUND_RE = re.compile(
    r"\b(R\d+|QF|SF|F|Final|1/\d+|Round\s+\d+|Группа\s+[A-ZА-Я]|Group\s+[A-Z])\b",
    re.I,
)


def parse_sports_entities(
    safe_text: str,
    injection: InjectionScanResult,
) -> StructuredCompetitionData:
    lines = [ln.strip() for ln in safe_text.split("\n") if ln.strip()]
    tournament = lines[0][:120] if lines else None
    date_m = _DATE_RE.search(safe_text)
    date = date_m.group(1) if date_m else None

    matches: list[MatchEntry] = []
    scores: list[str] = []
    rounds: list[str] = []

    for line in lines:
        rm = _ROUND_RE.search(line)
        if rm:
            r = rm.group(1)
            if r not in rounds:
                rounds.append(r)

        for sm in _SCORE_RE.finditer(line):
            sc = f"{sm.group(1)}-{sm.group(2)}"
            if sc not in scores:
                scores.append(sc)

        vm = _VS_RE.search(line)
        if vm:
            sc = None
            sm = _SCORE_RE.search(line)
            if sm:
                sc = f"{sm.group(1)}-{sm.group(2)}"
            matches.append(
                MatchEntry(
                    round=rm.group(1) if rm else None,
                    player_a=vm.group(1).strip(),
                    player_b=vm.group(2).strip(),
                    score=sc,
                )
            )

    table_matches, table_scores, table_debug = parse_table_matches(lines)
    if table_matches:
        seen = {(m.player_a, m.player_b, m.score) for m in matches}
        for m in table_matches:
            key = (m.player_a, m.player_b, m.score)
            if key not in seen:
                matches.append(m)
                seen.add(key)
    for sc in table_scores:
        if sc not in scores:
            scores.append(sc)

    parse_debug: dict[str, Any] | None = None
    if table_debug.get("detected_table_format") or table_debug.get("parsed_rows"):
        parse_debug = table_debug

    security_flag = "prompt_injection_detected" if injection.detected else None
    notice = None
    if injection.detected:
        notice = "В документе найден подозрительный текст, он был проигнорирован."

    return StructuredCompetitionData(
        tournament_name=tournament,
        date=date,
        match_list=matches[:80],
        scores=scores[:40],
        rounds=rounds[:20],
        player_results=[],
        insights=[],
        recommendations=[],
        security_flag=security_flag,
        security_notice=notice,
        parse_debug=parse_debug,
    )


def merge_gemini_structured(
    base: StructuredCompetitionData,
    gemini_data: dict[str, Any],
) -> StructuredCompetitionData:
    """Merge LLM fields without replacing security flags from parser."""
    if gemini_data.get("tournament_name"):
        base.tournament_name = str(gemini_data["tournament_name"])[:200]
    if gemini_data.get("date"):
        base.date = str(gemini_data["date"])[:32]
    ml = gemini_data.get("match_list") or []
    if isinstance(ml, list) and ml:
        parsed: list[MatchEntry] = []
        for m in ml[:80]:
            if isinstance(m, dict):
                parsed.append(MatchEntry(**{k: m.get(k) for k in MatchEntry.model_fields}))
        if parsed:
            base.match_list = parsed
    for key in ("rounds", "scores", "insights", "recommendations", "player_results"):
        val = gemini_data.get(key)
        if isinstance(val, list) and val:
            setattr(base, key, val[:40] if key != "player_results" else val[:40])
    return base


def structured_to_json(data: StructuredCompetitionData) -> str:
    return json.dumps(data.model_dump(mode="json"), ensure_ascii=False, indent=2)
