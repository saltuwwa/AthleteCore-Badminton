from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

DocumentAction = Literal["parse_results", "find_my_matches", "compare_past"]
DetectedDocType = Literal["pdf", "docx", "xlsx", "csv", "image", "unknown"]


class DocumentUploadResponse(BaseModel):
    document_id: str
    filename: str
    detected_type: DetectedDocType
    size_bytes: int


class MatchEntry(BaseModel):
    round: str | None = None
    player_a: str | None = None
    player_b: str | None = None
    score: str | None = None
    winner: str | None = None


class StructuredCompetitionData(BaseModel):
    tournament_name: str | None = None
    date: str | None = None
    match_list: list[MatchEntry] = Field(default_factory=list)
    scores: list[str] = Field(default_factory=list)
    rounds: list[str] = Field(default_factory=list)
    player_results: list[dict[str, Any]] = Field(default_factory=list)
    insights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    security_flag: str | None = None
    security_notice: str | None = None


class DocumentAnalyzeRequest(BaseModel):
    document_id: str
    user_id: str = "aigerim"
    action: DocumentAction = "parse_results"
    athlete_name: str | None = None


class DocumentAnalyzeResponse(BaseModel):
    document_id: str
    action: DocumentAction
    detected_type: DetectedDocType
    structured: StructuredCompetitionData
    assistant_message: str
    memory_saved: bool = False
