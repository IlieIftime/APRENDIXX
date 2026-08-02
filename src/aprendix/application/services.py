"""Sprint 2 event-ingestion and attempt-submission use cases."""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from aprendix.application.contracts import (
    AttemptDTO,
    EventDTO,
    SubmissionReceipt,
    SubmitAttemptCommand,
)
from aprendix.application.ports import EventObserver, EventSink, SubmissionStore
from aprendix.domain import AttemptStatus, EventType


class EventIngestionService:
    """Validate and append immutable internal events through an application port."""

    def __init__(
        self,
        sink: EventSink,
        observers: tuple[EventObserver, ...] = (),
    ) -> None:
        self._sink = sink
        self._observers = observers

    def ingest(self, event: EventDTO) -> bool:
        created = self._sink.append(event)
        for observer in self._observers:
            observer.update_node_stats(event)
        return created


class AttemptSubmissionService:
    """Create an attempt and its event as one idempotent atomic operation."""

    def __init__(
        self,
        store: SubmissionStore,
        observers: tuple[EventObserver, ...] = (),
    ) -> None:
        self._store = store
        self._observers = observers

    def submit(self, command: SubmitAttemptCommand) -> SubmissionReceipt:
        attempt = AttemptDTO(
            id=command.attempt_id,
            idempotency_key=command.idempotency_key,
            user_id=command.user_id,
            exercise_id=command.exercise_id,
            status=AttemptStatus.SUBMITTED,
            source_code=command.source_code,
            duration_ms=command.duration_ms,
            submitted_at=command.submitted_at,
            created_at=command.submitted_at,
        )
        event_id = uuid5(
            NAMESPACE_URL,
            f"aprendix:attempt-submitted:{command.attempt_id}",
        )
        event = EventDTO(
            id=event_id,
            idempotency_key=command.idempotency_key,
            user_id=command.user_id,
            event_type=EventType.ATTEMPT_SUBMITTED,
            payload={
                "attempt_id": str(command.attempt_id),
                "exercise_id": str(command.exercise_id),
                "duration_ms": command.duration_ms,
            },
            occurred_at=command.submitted_at,
            created_at=command.submitted_at,
        )
        created = self._store.record(attempt, event)
        for observer in self._observers:
            observer.update_node_stats(event)
        return SubmissionReceipt(
            attempt_id=attempt.id,
            event_id=event.id,
            created=created,
        )
