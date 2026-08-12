"""Contracts for a resumable objective-level learning session."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import Field

from aprendix.application.contracts.models import ContractModel, utc_now
from aprendix.domain.enums import StrEnum


class LearningPhase(StrEnum):
    MICROTHEORY = "microtheory"
    PREDICTION = "prediction"
    GUIDED_PRACTICE = "guided_practice"
    INDEPENDENT_PRACTICE = "independent_practice"
    REFLECTION = "reflection"
    REVIEW = "review"
    COMPLETED = "completed"


class LearningSessionDTO(ContractModel):
    user_id: UUID
    exercise_id: UUID
    unit_id: str = Field(default="", max_length=160)
    objective_id: str = Field(default="", max_length=160)
    objective_code: str = Field(default="", max_length=80)
    objective_description: str = Field(default="", max_length=500)
    phase: LearningPhase = LearningPhase.MICROTHEORY
    mode: str = Field(default="training", pattern=r"^(training|evaluation)$")
    theory_viewed: bool = False
    independent_passed: bool = False
    transfer_passed: bool = False
    hint_count: int = Field(default=0, ge=0, le=100)
    active_seconds: int = Field(default=0, ge=0, le=86_400)
    prediction: str = Field(default="", max_length=4_000)
    reflection: str = Field(default="", max_length=4_000)
    started_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
