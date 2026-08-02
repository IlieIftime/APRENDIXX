"""Stable domain enumerations persisted by the application."""

from enum import StrEnum


class EventType(StrEnum):
    """Kinds of immutable user activity accepted by the event store."""

    USER_CREATED = "user.created"
    EXERCISE_OPENED = "exercise.opened"
    CODE_EDITED = "code.edited"
    HINT_REQUESTED = "hint.requested"
    ATTEMPT_SUBMITTED = "attempt.submitted"
    ATTEMPT_EVALUATED = "attempt.evaluated"
    ASSESSMENT_EVALUATED = "assessment.evaluated"


class AttemptStatus(StrEnum):
    """Lifecycle state of a submitted programming attempt."""

    DRAFT = "draft"
    SUBMITTED = "submitted"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
