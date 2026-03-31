from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class InspectFrame(BaseModel):
    frame_index: int = Field(ge=0)
    timestamp_ms: int = Field(ge=0)
    timestamp_label: str = Field(..., min_length=1, max_length=32)
    image_base64: str = Field(..., min_length=16)


class InspectCriterion(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(..., min_length=1, max_length=400)


class InspectCandidate(BaseModel):
    clip_id: str = Field(..., min_length=1, max_length=128)
    asset_id: str = Field(..., min_length=1, max_length=128)
    clip_duration_ms: int = Field(..., gt=0)
    summary: str | None = Field(default=None, max_length=1000)
    frames: list[InspectFrame] = Field(default_factory=list)


class InspectRequest(BaseModel):
    mode: Literal["verify", "compare", "choose", "rank"]
    task_summary: str = Field(..., min_length=1, max_length=2000)
    hypothesis_summary: str | None = Field(default=None, max_length=2000)
    question: str = Field(..., min_length=1, max_length=2000)
    criteria: list[InspectCriterion] = Field(default_factory=list)
    candidates: list[InspectCandidate] = Field(default_factory=list)


class CandidateJudgment(BaseModel):
    clip_id: str = Field(..., min_length=1, max_length=128)
    verdict: Literal["match", "partial_match", "mismatch"]
    confidence: float | None = Field(default=None, ge=0, le=1)
    short_reason: str = Field(..., min_length=1, max_length=500)


class InspectResponse(BaseModel):
    question_type: Literal["verify", "compare", "choose", "rank"]
    selected_clip_id: str | None = Field(default=None, min_length=1, max_length=128)
    ranking: list[str] | None = None
    candidate_judgments: list[CandidateJudgment] = Field(..., min_length=1)
    uncertainty: str | None = Field(default=None, max_length=1000)
