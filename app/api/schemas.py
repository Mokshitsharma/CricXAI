"""Pydantic request/response models for the v1 API."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.utils.cricket_constants import BOWLER_TYPES


class MatchSituation(BaseModel):
    innings: int = Field(ge=1, le=2, description="1 = batting first, 2 = chasing")
    over: int = Field(ge=0, le=49)
    ball_in_over: int = Field(default=1, ge=1, le=6)
    score: int = Field(ge=0)
    wickets: int = Field(default=0, ge=0, le=9)
    target: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def _check_target(self) -> MatchSituation:
        if self.innings == 2 and self.target is None:
            raise ValueError("target is required when innings == 2")
        if self.target is not None and self.target <= self.score:
            raise ValueError("target must be greater than the current score")
        return self


class RecommendationOptions(BaseModel):
    top_k: int = Field(default=3, ge=1, le=5)


class RecommendationRequest(BaseModel):
    match: MatchSituation
    batsman_id: str | None = None
    batsman: str | None = None
    bowler_type: str
    options: RecommendationOptions = RecommendationOptions()

    @model_validator(mode="after")
    def _check(self) -> RecommendationRequest:
        if not (self.batsman_id or self.batsman):
            raise ValueError("provide batsman_id or batsman")
        if self.bowler_type not in BOWLER_TYPES:
            raise ValueError(f"bowler_type must be one of {list(BOWLER_TYPES)}")
        return self


class DismissalPredictRequest(BaseModel):
    match: MatchSituation
    batsman_id: str | None = None
    batsman: str | None = None
    bowler_type: str
    length: str
    line: str

    @model_validator(mode="after")
    def _check(self) -> DismissalPredictRequest:
        if not (self.batsman_id or self.batsman):
            raise ValueError("provide batsman_id or batsman")
        return self


class SituationSummary(BaseModel):
    phase: str
    pressure_index: float
    low_sample: bool
    batsman: str
    bowler_type: str


class FieldPosition(BaseModel):
    name: str
    x: float
    y: float


class RecommendationItem(BaseModel):
    rank: int
    length: str
    line: str
    label: str
    dismissal_probability: float
    dismissal_type_top: str
    dismissal_type_distribution: dict[str, float]
    expected_runs: float
    field_preset: str
    field_label: str
    field_positions: list[FieldPosition]
    reasons: list[str]
    confidence: str
    score: float


class RecommendationResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_version: str
    situation: SituationSummary
    recommendations: list[RecommendationItem]


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
