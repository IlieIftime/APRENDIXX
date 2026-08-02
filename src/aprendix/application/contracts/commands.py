"""Commands and receipts for Sprint 2 application use cases."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import Field, model_validator

from aprendix.application.contracts.models import ContractModel, utc_now


class SubmitAttemptCommand(ContractModel):
    """Validated intent to persist a programming exercise submission."""

    attempt_id: UUID = Field(default_factory=uuid4)
    idempotency_key: UUID = Field(default_factory=uuid4)
    user_id: UUID
    exercise_id: UUID
    source_code: str = Field(min_length=1, max_length=100_000)
    duration_ms: int = Field(ge=0)
    submitted_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def source_must_contain_code(self) -> SubmitAttemptCommand:
        if not self.source_code.strip():
            raise ValueError("source_code cannot be blank")
        return self


class SubmissionReceipt(ContractModel):
    """Stable result returned for both first writes and idempotent replays."""

    attempt_id: UUID
    event_id: UUID
    created: bool

