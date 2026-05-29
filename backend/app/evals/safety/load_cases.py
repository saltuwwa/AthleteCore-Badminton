"""Load safety eval cases from JSON/YAML golden datasets."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .schemas import SafetyCase, SafetyCaseFile

_GOLDEN_DIR = Path(__file__).resolve().parent.parent / "golden_datasets"

_DEFAULT_FILES = (
    _GOLDEN_DIR / "generic_safety_baseline.json",
    _GOLDEN_DIR / "athletecore_safety_cases.json",
)


def _parse_raw(data: dict[str, Any]) -> list[SafetyCase]:
    if "cases" in data:
        return SafetyCaseFile.model_validate(data).cases
    if isinstance(data.get("case"), dict):
        return [SafetyCase.model_validate(data["case"])]
    raise ValueError("Dataset must contain 'cases' array")


def load_cases_from_path(path: str | Path) -> list[SafetyCase]:
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)

    raw_text = path.read_text(encoding="utf-8")
    suffix = path.suffix.lower()
    if suffix in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as e:
            raise ImportError(
                "PyYAML required for YAML datasets: pip install pyyaml"
            ) from e
        data = yaml.safe_load(raw_text)
    else:
        data = json.loads(raw_text)

    cases = _parse_raw(data)
    return [c for c in cases if c.enabled]


def load_all_safety_cases(
    *,
    extra_paths: list[str | Path] | None = None,
    include_defaults: bool = True,
) -> list[SafetyCase]:
    paths: list[Path] = []
    if include_defaults:
        paths.extend(_DEFAULT_FILES)
    if extra_paths:
        paths.extend(Path(p) for p in extra_paths)

    seen: set[str] = set()
    out: list[SafetyCase] = []
    for p in paths:
        if not p.is_file():
            continue
        for case in load_cases_from_path(p):
            if case.id in seen:
                raise ValueError(f"Duplicate safety case id: {case.id}")
            seen.add(case.id)
            out.append(case)
    return out
