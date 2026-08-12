"""Contracts for trustworthy sources, revisions and curriculum coverage."""

from __future__ import annotations

from datetime import datetime
from aprendix.domain.enums import StrEnum
from uuid import UUID

from pydantic import Field

from aprendix.application.contracts.models import ContractModel, NonBlankText, utc_now


class AuthorityLevel(StrEnum):
    PRIMARY = "primary"
    REVIEWED = "reviewed"
    PREPRINT = "preprint"
    LOCAL_PRIVATE = "local-private"


class GapCode(StrEnum):
    NONE = "none"
    NEEDS_THEORY = "needs-theory"
    NEEDS_PRACTICE = "needs-practice"
    NEEDS_BOTH = "needs-both"


class ContentSourceDTO(ContractModel):
    id: NonBlankText = Field(max_length=80, pattern=r"^[a-z0-9.-]+$")
    domain: NonBlankText = Field(max_length=253)
    allowed_content_types: tuple[str, ...] = Field(max_length=12)
    license_policy: NonBlankText = Field(max_length=500)
    robots_policy: NonBlankText = Field(max_length=300)
    parser_version: NonBlankText = Field(max_length=80)
    change_detection: NonBlankText = Field(max_length=160)
    authority_level: AuthorityLevel
    enabled: bool = True
    updated_at: datetime = Field(default_factory=utc_now)


class CurriculumCoverageDTO(ContractModel):
    objective_id: UUID
    objective_code: NonBlankText = Field(max_length=120)
    objective: NonBlankText = Field(max_length=500)
    theory_evidence_count: int = Field(ge=0)
    card_count: int = Field(ge=0)
    exercise_count: int = Field(ge=0)
    coverage_score: float = Field(ge=0.0, le=1.0)
    gap_code: GapCode
    measured_at: datetime = Field(default_factory=utc_now)


class BibliographyCoverageDTO(ContractModel):
    objective_count: int = Field(ge=0)
    covered_objectives: int = Field(ge=0)
    triple_sourced_objectives: int = Field(ge=0)
    authoritative_objectives: int = Field(ge=0)
    distinct_sources: int = Field(ge=0)
    coverage_score: float = Field(ge=0.0, le=1.0)
    weak_objective_codes: tuple[str, ...] = Field(default=(), max_length=500)
    measured_at: datetime = Field(default_factory=utc_now)
