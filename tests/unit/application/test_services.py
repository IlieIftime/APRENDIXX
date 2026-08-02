"""Application service tests independent from SQLite details."""

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from aprendix.application.contracts import EventDTO, SubmitAttemptCommand
from aprendix.application.services import (
    AttemptSubmissionService,
    EventIngestionService,
)
from aprendix.domain import EventType


class CapturingEventSink:
    def __init__(self) -> None:
        self.events: list[EventDTO] = []

    def append(self, event: EventDTO) -> bool:
        self.events.append(event)
        return True


class CapturingSubmissionStore:
    def __init__(self) -> None:
        self.calls = []

    def record(self, attempt, event) -> bool:
        self.calls.append((attempt, event))
        return True


def test_event_ingestion_delegates_valid_contract() -> None:
    sink = CapturingEventSink()
    service = EventIngestionService(sink)
    event = EventDTO(
        user_id=uuid4(),
        event_type=EventType.EXERCISE_OPENED,
        payload={"exercise_id": str(uuid4())},
    )

    assert service.ingest(event) is True
    assert sink.events == [event]


def test_event_ingestion_notifies_graph_observer_on_replay() -> None:
    sink = CapturingEventSink()
    sink.append = lambda _event: False

    class Observer:
        def __init__(self):
            self.events = []

        def update_node_stats(self, event):
            self.events.append(event)

    observer = Observer()
    service = EventIngestionService(sink, observers=(observer,))
    event = EventDTO(
        user_id=uuid4(),
        event_type=EventType.EXERCISE_OPENED,
        payload={"exercise_id": str(uuid4())},
    )

    assert service.ingest(event) is False
    assert observer.events == [event]


def test_submission_maps_command_without_source_in_event() -> None:
    store = CapturingSubmissionStore()
    service = AttemptSubmissionService(store)
    command = SubmitAttemptCommand(
        user_id=uuid4(),
        exercise_id=uuid4(),
        source_code="print('segredo')",
        duration_ms=1250,
        submitted_at=datetime(2026, 2, 1, tzinfo=UTC),
    )

    receipt = service.submit(command)
    attempt, event = store.calls[0]

    assert receipt.attempt_id == command.attempt_id
    assert receipt.created is True
    assert attempt.source_code == "print('segredo')"
    assert event.event_type is EventType.ATTEMPT_SUBMITTED
    assert event.payload["attempt_id"] == str(command.attempt_id)
    assert "source_code" not in event.payload
    assert "segredo" not in event.to_json()


def test_submission_command_rejects_blank_source() -> None:
    with pytest.raises(ValueError, match="at least 1 character"):
        SubmitAttemptCommand(
            user_id=uuid4(),
            exercise_id=uuid4(),
            source_code=" \n ",
            duration_ms=1,
        )
