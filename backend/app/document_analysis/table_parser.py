"""Parse tabular competition rows (TSV / CSV / markdown tables)."""

from __future__ import annotations

import re
from typing import Any

from app.document_analysis.schemas import MatchEntry

_SCORE_CELL_RE = re.compile(r"^\s*(\d{1,2})\s*[-:–]\s*(\d{1,2})\s*$")
_NAME_RE = re.compile(r"^[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё\s\.\-']{1,48}$")

_HEADER_HINTS = (
    ("player", "score"),
    ("player a", "player b"),
    ("athlete", "opponent"),
    ("opponent", "score"),
    ("игрок", "счёт"),
    ("счет",),
)


def _split_cells(line: str) -> list[str]:
    line = line.strip()
    if not line:
        return []
    if "\t" in line:
        return [c.strip() for c in line.split("\t") if c.strip()]
    if "|" in line and line.count("|") >= 2:
        parts = [c.strip() for c in line.split("|")]
        return [p for p in parts if p and not re.match(r"^[-:]+$", p)]
    if ";" in line and line.count(";") >= 2:
        return [c.strip() for c in line.split(";") if c.strip()]
    if "," in line and line.count(",") >= 2:
        return [c.strip() for c in line.split(",") if c.strip()]
    parts = re.split(r"\s{2,}", line)
    if len(parts) >= 3:
        return [p.strip() for p in parts if p.strip()]
    return [c.strip() for c in re.split(r"\s+", line) if c.strip()]


def _detect_format(sample_line: str) -> str:
    if "\t" in sample_line:
        return "tsv"
    if "|" in sample_line:
        return "markdown_table"
    if ";" in sample_line:
        return "semicolon"
    if "," in sample_line:
        return "csv"
    if re.search(r"\s{2,}", sample_line):
        return "multi_space"
    return "whitespace"


def _is_header_row(cells: list[str]) -> bool:
    joined = " ".join(cells).lower()
    if any(h in joined for h in ("player a", "player b", "player", "score", "opponent", "result")):
        return True
    if "игрок" in joined and ("счёт" in joined or "счет" in joined):
        return True
    non_numeric = sum(1 for c in cells if not _SCORE_CELL_RE.match(c))
    return non_numeric == len(cells) and len(cells) >= 2


def _parse_score_cell(cell: str) -> str | None:
    m = _SCORE_CELL_RE.match(cell.strip())
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None


def _looks_like_name(cell: str) -> bool:
    cell = cell.strip()
    if not cell or _SCORE_CELL_RE.match(cell):
        return False
    if len(cell) > 50:
        return False
    return bool(_NAME_RE.match(cell))


def parse_table_matches(lines: list[str]) -> tuple[list[MatchEntry], list[str], dict[str, Any]]:
    """
    Extract matches from spreadsheet-like rows.
    Returns (matches, scores, debug).
    """
    debug: dict[str, Any] = {
        "detected_table_format": None,
        "parsed_rows": [],
        "extracted_scores": [],
        "extracted_matches_count": 0,
    }
    matches: list[MatchEntry] = []
    scores: list[str] = []

    table_lines = [ln for ln in lines if ln.strip() and len(_split_cells(ln)) >= 2]
    if len(table_lines) < 2:
        return matches, scores, debug

    debug["detected_table_format"] = _detect_format(table_lines[0])
    start = 0
    first_cells = _split_cells(table_lines[0])
    if _is_header_row(first_cells):
        start = 1

    for line in table_lines[start:]:
        cells = _split_cells(line)
        if len(cells) < 2:
            continue

        score_cell: str | None = None
        name_a: str | None = None
        name_b: str | None = None

        if len(cells) >= 3:
            score_cell = _parse_score_cell(cells[-1])
            name_a = cells[0].strip() if _looks_like_name(cells[0]) else None
            name_b = cells[1].strip() if _looks_like_name(cells[1]) else None
        elif len(cells) == 2:
            if _SCORE_CELL_RE.match(cells[1]):
                score_cell = _parse_score_cell(cells[1])
                name_a = cells[0].strip() if _looks_like_name(cells[0]) else None
            elif _SCORE_CELL_RE.match(cells[0]):
                score_cell = _parse_score_cell(cells[0])
                name_b = cells[1].strip() if _looks_like_name(cells[1]) else None

        if not score_cell:
            for c in cells:
                sc = _parse_score_cell(c)
                if sc:
                    score_cell = sc
                    break

        if score_cell and score_cell not in scores:
            scores.append(score_cell)

        if name_a and name_b and score_cell:
            matches.append(
                MatchEntry(player_a=name_a, player_b=name_b, score=score_cell)
            )
            debug["parsed_rows"].append(
                {"player_a": name_a, "player_b": name_b, "score": score_cell}
            )
        elif name_a and score_cell and not name_b:
            matches.append(MatchEntry(player_a=name_a, player_b=None, score=score_cell))
            debug["parsed_rows"].append(
                {"player_a": name_a, "player_b": None, "score": score_cell}
            )

    debug["extracted_scores"] = scores[:40]
    debug["extracted_matches_count"] = len(matches)
    return matches, scores, debug
