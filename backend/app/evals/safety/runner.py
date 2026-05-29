"""Run hybrid safety eval suite."""

from __future__ import annotations

from pathlib import Path

from .checkers import run_case_checker
from .load_cases import load_all_safety_cases
from .report import build_report
from .schemas import SafetyEvalReport


def run_safety_eval(
    *,
    extra_paths: list[str | Path] | None = None,
    include_defaults: bool = True,
    category_filter: str | None = None,
    origin_filter: str | None = None,
) -> SafetyEvalReport:
    cases = load_all_safety_cases(
        extra_paths=extra_paths,
        include_defaults=include_defaults,
    )
    if category_filter:
        cases = [c for c in cases if c.category == category_filter]
    if origin_filter:
        cases = [c for c in cases if c.origin == origin_filter]

    results = [run_case_checker(c) for c in cases]
    return build_report(cases, results)
