"""Pydantic DTOs forming the internal JSON boundary between modules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)
from pydantic.types import JsonValue

from aprendix.domain.enums import AttemptStatus, EventType

NonBlankText = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]
Slug = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=80,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]


def utc_now() -> datetime:
    """Return an aware UTC timestamp suitable for persisted contracts."""

    return datetime.now(timezone.utc)


class ContractModel(BaseModel):
    """Strict, immutable base for versioned module contracts."""

    model_config = ConfigDict(
        allow_inf_nan=False,
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        use_enum_values=False,
    )

    schema_version: int = Field(default=1, ge=1, le=1)

    @field_validator("*", mode="after")
    @classmethod
    def require_aware_datetimes(cls, value: Any) -> Any:
        """Reject ambiguous local timestamps at every contract boundary."""

        if isinstance(value, datetime):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("timestamps must include a timezone")
            return value.astimezone(timezone.utc)
        return value

    def to_json(self) -> str:
        """Serialize with stable JSON representations for UUIDs and dates."""

        return self.model_dump_json()


class UserDTO(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    display_name: NonBlankText | None = Field(default=None, max_length=120)
    consent_sync: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def updated_not_before_creation(self) -> UserDTO:
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self


class EventDTO(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    idempotency_key: UUID = Field(default_factory=uuid4)
    user_id: UUID
    event_type: EventType
    payload: dict[str, JsonValue] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)


class ExerciseDTO(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    graph_node_id: UUID
    slug: Slug
    title: NonBlankText = Field(max_length=160)
    prompt: NonBlankText = Field(max_length=20_000)
    starter_code: str = Field(default="", max_length=50_000)
    tests: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    difficulty: float = Field(default=0.0, ge=-3.0, le=3.0)
    version: int = Field(default=1, ge=1)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("tests")
    @classmethod
    def tests_must_be_non_blank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not test.strip() for test in value):
            raise ValueError("exercise tests cannot contain blank entries")
        return value


class AttemptDTO(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    idempotency_key: UUID = Field(default_factory=uuid4)
    user_id: UUID
    exercise_id: UUID
    status: AttemptStatus = AttemptStatus.DRAFT
    source_code: str = Field(default="", max_length=100_000)
    output: str | None = Field(default=None, max_length=100_000)
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    duration_ms: int | None = Field(default=None, ge=0)
    submitted_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def validate_submission_state(self) -> AttemptDTO:
        completed = {
            AttemptStatus.PASSED,
            AttemptStatus.FAILED,
            AttemptStatus.ERROR,
        }
        if self.status is not AttemptStatus.DRAFT and self.submitted_at is None:
            raise ValueError("submitted and completed attempts require submitted_at")
        return self


class GraphNodeDTO(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    slug: Slug
    title: NonBlankText = Field(max_length=160)
    description: str = Field(default="", max_length=4_000)
    difficulty: float = Field(default=0.0, ge=-3.0, le=3.0)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class GraphEdgeDTO(ContractModel):
    source_node_id: UUID
    target_node_id: UUID
    weight: float = Field(default=0.0, ge=0.0)
    co_occurrence_count: int = Field(default=0, ge=0)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def reject_self_edge(self) -> GraphEdgeDTO:
        if self.source_node_id == self.target_node_id:
            raise ValueError("graph edges cannot point to the same node")
        return self


class ProfileDTO(ContractModel):
    user_id: UUID
    theta: float = Field(default=0.0, ge=-6.0, le=6.0)
    xp: int = Field(default=0, ge=0)
    streak_days: int = Field(default=0, ge=0)
    preferences: dict[str, JsonValue] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
