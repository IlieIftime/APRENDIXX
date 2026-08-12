"""Stable contracts for separating content access from curricular credit."""

from __future__ import annotations

from aprendix.domain.enums import StrEnum
from pydantic import Field

from aprendix.application.contracts.models import ContractModel


class LearningAccessReason(StrEnum):
    """Machine-readable reasons used by every learning surface."""

    ELIGIBLE = "eligible"
    COMPLETED = "completed"
    PREREQUISITES_INCOMPLETE = "prerequisites_incomplete"
    STANDALONE_PRACTICE = "standalone_practice"
    PROJECT_EVALUATION_REQUIRED = "project_evaluation_required"
    PROJECT_NOT_CAPSTONE = "project_not_capstone"
    PROJECT_TEMPLATE_MISMATCH = "project_template_mismatch"
    PROJECT_DOMAIN_CONTRACT_FAILED = "project_domain_contract_failed"
    PROJECT_MILESTONES_INCOMPLETE = "project_milestones_incomplete"
    NOT_APPLICABLE = "not_applicable"


class LearningAccessDTO(ContractModel):
    """Independent read, eligibility and completion state for one resource."""

    resource_id: str = Field(default="", max_length=160)
    resource_kind: str = Field(default="unknown", max_length=40)
    track_slug: str = Field(default="", max_length=120)
    viewable: bool = True
    credit_eligible: bool = False
    completed: bool = False
    reason_code: LearningAccessReason = LearningAccessReason.NOT_APPLICABLE
    missing_prerequisite_ids: tuple[str, ...] = Field(default=(), max_length=200)
