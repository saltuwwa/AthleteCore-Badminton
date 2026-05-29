"""Tests for hybrid AthleteCore safety eval harness."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evals.safety.load_cases import load_all_safety_cases, load_cases_from_path
from app.evals.safety.runner import run_safety_eval

_GOLDEN = Path(__file__).resolve().parents[1] / "app" / "evals" / "golden_datasets"


def test_load_default_cases_count():
    cases = load_all_safety_cases()
    assert len(cases) == 25


def test_no_duplicate_ids():
    cases = load_all_safety_cases()
    ids = [c.id for c in cases]
    assert len(ids) == len(set(ids))


def test_each_case_has_rubric_fields():
    cases = load_all_safety_cases()
    for c in cases:
        assert c.why_it_matters.strip()
        assert c.expected_safe_behavior.strip()
        assert c.pass_criteria.strip()
        assert c.fail_criteria.strip()
        assert c.severity in ("critical", "high", "medium", "low")


def test_origin_split():
    cases = load_all_safety_cases()
    generic = [c for c in cases if c.origin == "generic"]
    ac = [c for c in cases if c.origin == "athletecore"]
    assert len(generic) == 20
    assert len(ac) == 5
    assert len(ac) / len(cases) >= 0.2


def test_run_safety_eval_produces_report():
    report = run_safety_eval()
    assert report.total_cases == 25
    assert report.overall_pass_rate >= 0.0
    assert 0.0 <= report.generic_safety_score <= 1.0
    assert 0.0 <= report.athletecore_safety_score <= 1.0
    assert report.readiness_for_athletes in (
        "not_ready",
        "pilot_only",
        "pilot_with_guards",
        "pilot_ready",
    )
    assert len(report.by_category) >= 1


def test_import_json_fragment(tmp_path: Path):
    extra = tmp_path / "imported.json"
    extra.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "cases": [
                    {
                        "id": "import-001",
                        "title": "Imported benchmark case",
                        "category": "hallucination_resistance",
                        "origin": "imported",
                        "why_it_matters": "Validates external JSON import path.",
                        "expected_safe_behavior": "Policy-only stub passes.",
                        "pass_criteria": "Checker returns pass.",
                        "fail_criteria": "Loader or runner crashes.",
                        "severity": "low",
                        "checker": "policy_note",
                        "input": {},
                        "expect": {},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    cases = load_all_safety_cases(extra_paths=[extra])
    assert any(c.id == "import-001" for c in cases)
    report = run_safety_eval(extra_paths=[extra])
    assert report.total_cases == 26


def test_category_distribution():
    cases = load_all_safety_cases()
    cats = {c.category for c in cases}
    expected = {
        "document_parsing_quality",
        "indirect_prompt_injection",
        "rag_grounding",
        "hallucination_resistance",
        "medical_training_safety",
        "privacy_and_data_leakage",
        "video_analysis_reliability",
    }
    assert expected <= cats


def test_athletecore_file_loads():
    ac = load_cases_from_path(_GOLDEN / "athletecore_safety_cases.json")
    assert len(ac) == 5
    assert all(c.origin == "athletecore" for c in ac)
