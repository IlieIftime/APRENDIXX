"""Versioned contracts for the evidence-grounded offline tutor."""

from __future__ import annotations

from enum import Enum
from uuid import UUID, uuid4

from pydantic import Field

from aprendix.application.contracts.knowledge import SearchEvidenceDTO
from aprendix.application.contracts.models import ContractModel, NonBlankText


class TutorStrategy(str, Enum):
    EXPLAIN_DIFFERENTLY = "explain_differently"
    SOCRATIC = "socratic"
    NEW_EXAMPLE = "new_example"
    PREREQUISITE = "prerequisite"
    SIMPLIFY_MATH = "simplify_math"
    ANALYZE_ERROR = "analyze_error"
    MINI_EXERCISE = "mini_exercise"


class TutorRequestDTO(ContractModel):
    question: NonBlankText = Field(max_length=4_000)
    strategy: TutorStrategy = TutorStrategy.EXPLAIN_DIFFERENTLY
    learner_level: str = Field(default="beginner", pattern=r"^(beginner|intermediate|advanced)$")
    evaluation_locked: bool = False


class TutorResponseDTO(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    answer: NonBlankText = Field(max_length=20_000)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: tuple[SearchEvidenceDTO, ...] = Field(default=(), max_length=8)
    strategy: TutorStrategy
    declined: bool = False
    refusal_reason: str | None = Field(default=None, max_length=500)
    from_cache: bool = False
