"""Pydantic types shared across the pipeline, API, and UI."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Theme(BaseModel):
    id: str
    name: str
    summary: str
    frequency: int
    sentiment_score: float
    trend: str | None = None
    evidence: list[str] = Field(default_factory=list)
    score: float = 0.0
    score_breakdown: dict[str, float] = Field(default_factory=dict)


class Recommendation(BaseModel):
    id: str
    title: str
    action: str
    rationale: str
    evidence: list[str] = Field(default_factory=list)
    score: float
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    source_theme_id: str
    theme_key: str = ""
    memory_citations: list[str] = Field(default_factory=list)


class Brief(BaseModel):
    batch: int
    date: str
    summary: str
    recommendations: list[Recommendation]
    generated_with_memory: bool
    pm_preferences_applied: list[str] = Field(default_factory=list)


class RecalledMemory(BaseModel):
    purpose: str
    query: str
    text: str
    score: float | None = None
    metadata: dict[str, Any] | None = None


class AnalysisResult(BaseModel):
    batch: int
    memory_enabled: bool
    date: str
    themes: list[Theme]
    brief: Brief
    recalled_memories: list[RecalledMemory] = Field(default_factory=list)
    cached: bool = False
    warning: str | None = None


ContextCategory = Literal[
    "shipped", "roadmap", "constraint", "target_user", "preference"
]
PMDecisionKind = Literal["accepted", "rejected", "edited"]
