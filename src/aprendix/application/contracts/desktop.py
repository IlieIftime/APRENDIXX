"""Contracts for the integrated desktop learning workspace."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import Field

from aprendix.application.contracts.models import ContractModel, NonBlankText, utc_now
from aprendix.application.contracts.knowledge import LearningTheme, Technology


class LearnerRank(StrEnum):
    INITIATE = "iniciante"
    ADEPT = "adepto"
    PROFICIENT = "proficiente"
    EXPERT = "especialista"


class MilestoneProgressDTO(ContractModel):
    id: str = Field(min_length=1, max_length=160)
    technology: Technology
    theme: LearningTheme
    rank_from: LearnerRank
    rank_to: LearnerRank
    completed: int = Field(ge=0)
    required: int = Field(gt=0)
    achieved: bool = False


class ProjectDTO(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    user_id: UUID
    name: NonBlankText = Field(max_length=160)
    technology: Technology = Technology.PYTHON
    relative_path: str = Field(default="main.py", pattern=r"^[A-Za-z0-9_.-]{1,120}$")
    source_code: str = Field(default="", max_length=100_000)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class EvaluationReceiptDTO(ContractModel):
    attempt_id: UUID
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    feedback: tuple[str, ...] = Field(default=(), max_length=100)
    milestone: MilestoneProgressDTO | None = None

