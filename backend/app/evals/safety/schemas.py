"""Pydantic models for hybrid safety eval cases and reports."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

SafetyCategory = Literal[
    "document_parsing_quality",
    "indirect_prompt_injection",
    "rag_grounding",
    "hallucination_resistance",
    "medical_training_safety",
    "privacy_and_data_leakage",
    "video_analysis_reliability",
]

CaseOrigin = Literal["generic", "athletecore", "imported"]
Severity = Literal["critical", "high", "medium", "low"]

CheckerKind = Literal[
    "injection_scan",
    "document_parse",
    "memory_payload",
    "gemini_blob",
    "forbidden_patterns",
    "required_patterns",
    "prompt_safety_anchor",
    "rag_context_format",
    "methodology_retrieval",
    "video_selection_eval",
    "policy_note",
]


class SafetyCaseExpect(BaseModel):
    """Checker-specific expectations (flexible dict)."""

    detected: bool | None = None
    security_flag: str | None = None
    min_matches: int | None = None
    forbidden_substrings: list[str] = Field(default_factory=list)
    required_substrings: list[str] = Field(default_factory=list)
    forbidden_regex: list[str] = Field(default_factory=list)
    required_regex: list[str] = Field(default_factory=list)
    anchor_files: list[str] = Field(default_factory=list)
    anchor_substrings: list[str] = Field(default_factory=list)
    max_snippet_score: float | None = None
    min_selection_warnings: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class SafetyCaseInput(BaseModel):
    text: str | None = None
    user_instruction: str | None = None
    athlete_name: str | None = None
    query: str | None = None
    poisoned_chunk: str | None = None
    document_id: str | None = None
    video_eval: dict[str, Any] | None = None
    fixture_response: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class SafetyCase(BaseModel):
    id: str
    title: str
    category: SafetyCategory
    origin: CaseOrigin = "generic"
    standard_category: str | None = None
    why_it_matters: str
    expected_safe_behavior: str
    pass_criteria: str
    fail_criteria: str
    severity: Severity = "medium"
    checker: CheckerKind
    input: SafetyCaseInput = Field(default_factory=SafetyCaseInput)
    expect: SafetyCaseExpect = Field(default_factory=SafetyCaseExpect)
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True


class SafetyCaseFile(BaseModel):
    schema_version: int = 1
    dataset: str = "unknown"
    description: str | None = None
    cases: list[SafetyCase]


class CaseResult(BaseModel):
    case_id: str
    title: str
    category: SafetyCategory
    origin: CaseOrigin
    severity: Severity
    passed: bool
    message: str
    details: dict[str, Any] = Field(default_factory=dict)
    recommended_fix: str | None = None


class CategoryStats(BaseModel):
    category: SafetyCategory
    total: int
    passed: int
    failed: int
    pass_rate: float


class SafetyEvalReport(BaseModel):
    schema_version: int = 1
    total_cases: int
    passed: int
    failed: int
    overall_pass_rate: float
    generic_safety_score: float
    athletecore_safety_score: float
    by_category: list[CategoryStats]
    results: list[CaseResult]
    failed_examples: list[CaseResult]
    recommended_fixes: list[str]
    readiness_for_athletes: str
    readiness_rationale: str
    notes: list[str] = Field(default_factory=list)
