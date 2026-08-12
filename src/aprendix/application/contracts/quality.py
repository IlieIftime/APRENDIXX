"""Contracts for the automatic pedagogical quality compiler."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from aprendix.application.contracts.models import ContractModel, NonBlankText, utc_now


class QualityCheckDTO(ContractModel):
    code: NonBlankText = Field(max_length=80)
    passed: bool
    critical: bool = False
    detail: NonBlankText = Field(max_length=500)


class PedagogicalQualityDTO(ContractModel):
    item_type: Literal["exercise", "project", "card", "unit"]
    item_id: NonBlankText = Field(max_length=180)
    quality_score: float = Field(ge=0.0, le=1.0)
    estimated_difficulty: float = Field(ge=-3.0, le=3.0)
    status: Literal["accepted", "quarantined"]
    generator_version: NonBlankText = Field(max_length=100)
    checks: tuple[QualityCheckDTO, ...] = Field(min_length=1, max_length=30)


class PedagogicalQualityAuditDTO(ContractModel):
    fingerprint: str = Field(min_length=64, max_length=64)
    total: int = Field(ge=0)
    accepted: int = Field(ge=0)
    quarantined: int = Field(ge=0)
    average_score: float = Field(ge=0.0, le=1.0)
    by_type: dict[str, int] = Field(default_factory=dict)
    generated_at: datetime = Field(default_factory=utc_now)

