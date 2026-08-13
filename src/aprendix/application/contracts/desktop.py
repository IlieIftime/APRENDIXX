"""Contracts for the integrated desktop learning workspace."""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from aprendix.application.contracts.access import LearningAccessDTO
from aprendix.application.contracts.knowledge import LearningTheme, Technology
from aprendix.application.contracts.models import ContractModel, NonBlankText, utc_now
from aprendix.application.contracts.progress import ErrorCategory
from aprendix.domain.enums import StrEnum


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
    relative_path: str = Field(default="main.py", min_length=1, max_length=240)
    source_code: str = Field(default="", max_length=100_000)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        normalized = value.strip().replace("\\", "/")
        parts = normalized.split("/")
        if (
            normalized.startswith("/") or normalized.endswith("/")
            or any(part in {"", ".", ".."} for part in parts)
            or any(not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", part) for part in parts)
        ):
            raise ValueError("Caminho relativo inválido ou inseguro.")
        return normalized


class EvaluationReceiptDTO(ContractModel):
    attempt_id: UUID
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    feedback: tuple[str, ...] = Field(default=(), max_length=100)
    milestone: MilestoneProgressDTO | None = None
    attempt_number: int = Field(default=1, ge=1)
    failed_attempts: int = Field(default=0, ge=0)
    error_category: ErrorCategory = ErrorCategory.NONE
    assistance_stage: str = Field(default="", max_length=40)
    assistance_title: str = Field(default="", max_length=160)
    assistance: tuple[str, ...] = Field(default=(), max_length=10)
    next_action: str = Field(default="", max_length=500)
    worked_example: str = Field(default="", max_length=20_000)
    diagnostic_code: str = Field(default="", max_length=40)
    diagnosis_title: str = Field(default="", max_length=240)
    diagnosis: str = Field(default="", max_length=2_000)
    prerequisite_terms: tuple[str, ...] = Field(default=(), max_length=10)
    remediation_actions: tuple[str, ...] = Field(default=(), max_length=10)
    mini_exercise: str = Field(default="", max_length=2_000)
    improvement: str = Field(default="", max_length=1_000)
    reference_available: bool = False
    reference_solution: str = Field(default="", max_length=100_000)
    reference_explanation: str = Field(default="", max_length=20_000)
    reference_trace: tuple[str, ...] = Field(default=(), max_length=100)
    reference_expected_output: tuple[str, ...] = Field(default=(), max_length=20)
    reference_validation_hash: str = Field(default="", max_length=64)
    access: LearningAccessDTO = Field(default_factory=LearningAccessDTO)
    credit_awarded: bool = False
