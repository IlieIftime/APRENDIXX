"""Integration behavior for Sprint 2 encrypted repositories."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from aprendix.application.contracts import EventDTO, SubmitAttemptCommand, UserDTO
from aprendix.application.services import AttemptSubmissionService, EventIngestionService
from aprendix.domain import EventType
from aprendix.infrastructure.db import (
    AttemptRepository,
    Database,
    EventRepository,
    ExerciseRepository,
    LearningRecordRepository,
    UserRepository,
)
from aprendix.infrastructure.db.repositories import IdempotencyConflictError
from aprendix.infrastructure.security import AesGcmFieldCipher
from aprendix.infrastructure.seed import seed_default_catalog


@pytest.fixture
def sprint2_context(
    database: Database,
    cipher: AesGcmFieldCipher,
):
    seed_default_catalog(database)
    user = UserDTO(display_name="Ada")
    UserRepository(database, cipher).add(user)
    event_repository = EventRepository(database, cipher)
    attempt_repository = AttemptRepository(database, cipher)
    exercise = ExerciseRepository(database, cipher).list_all()[0]
    submission_service = AttemptSubmissionService(
        LearningRecordRepository(
            database,
            attempt_repository,
            event_repository,
        )
    )
    return (
        user,
        exercise,
        event_repository,
        attempt_repository,
        submission_service,
    )


def test_event_round_trip_is_encrypted_and_idempotent(
    database: Database,
    sprint2_context,
) -> None:
    user, exercise, events, _, _ = sprint2_context
    event = EventDTO(
        user_id=user.id,
        event_type=EventType.EXERCISE_OPENED,
        payload={"exercise_id": str(exercise.id), "label": "início 🧠"},
    )
    service = EventIngestionService(events)

    assert service.ingest(event) is True
    assert service.ingest(event) is False
    assert events.get(event.id) == event

    with database.read_connection() as connection:
        row = connection.execute(
            "SELECT payload_encrypted FROM events WHERE id = ?",
            (str(event.id),),
        ).fetchone()
        count = connection.execute("SELECT count(*) FROM events").fetchone()[0]

    assert count == 1
    assert b"exercise_id" not in row[0]
    assert "início".encode() not in row[0]


def test_event_idempotency_conflict_preserves_original(sprint2_context) -> None:
    user, exercise, events, _, _ = sprint2_context
    original = EventDTO(
        user_id=user.id,
        event_type=EventType.EXERCISE_OPENED,
        payload={"exercise_id": str(exercise.id)},
    )
    events.append(original)
    conflict = original.model_copy(
        update={"id": uuid4(), "payload": {"exercise_id": str(uuid4())}}
    )

    with pytest.raises(IdempotencyConflictError, match="different content"):
        events.append(conflict)

    assert events.list_for_user(user.id) == (original,)


def test_submission_is_atomic_encrypted_and_replay_safe(
    database: Database,
    sprint2_context,
) -> None:
    user, exercise, events, attempts, service = sprint2_context
    command = SubmitAttemptCommand(
        user_id=user.id,
        exercise_id=exercise.id,
        source_code="print('não executar')",
        duration_ms=900,
        submitted_at=datetime(2026, 3, 1, tzinfo=UTC),
    )

    first = service.submit(command)
    replay = service.submit(command)
    restored = attempts.get(first.attempt_id)
    submission_event = events.get(first.event_id)

    with database.read_connection() as connection:
        raw = connection.execute(
            """
            SELECT source_code_encrypted
            FROM attempts WHERE id = ?
            """,
            (str(first.attempt_id),),
        ).fetchone()[0]
        counts = (
            connection.execute("SELECT count(*) FROM attempts").fetchone()[0],
            connection.execute("SELECT count(*) FROM events").fetchone()[0],
        )

    assert first.created is True
    assert replay.created is False
    assert restored.source_code == command.source_code
    assert submission_event.payload["attempt_id"] == str(command.attempt_id)
    assert "source_code" not in submission_event.payload
    assert command.source_code.encode() not in raw
    assert counts == (1, 1)


def test_conflicting_attempt_replay_rolls_back_event(sprint2_context) -> None:
    user, exercise, events, attempts, service = sprint2_context
    command = SubmitAttemptCommand(
        user_id=user.id,
        exercise_id=exercise.id,
        source_code="print(1)",
        duration_ms=10,
    )
    service.submit(command)
    conflict = command.model_copy(
        update={
            "attempt_id": uuid4(),
            "source_code": "print(2)",
            "submitted_at": command.submitted_at + timedelta(seconds=1),
        }
    )

    with pytest.raises(IdempotencyConflictError):
        service.submit(conflict)

    assert len(attempts.list_for_user(user.id)) == 1
    assert len(events.list_for_user(user.id)) == 1


def test_event_failure_rolls_back_new_attempt(
    database: Database,
    cipher: AesGcmFieldCipher,
    sprint2_context,
) -> None:
    user, exercise, _, attempts, _ = sprint2_context

    class FailingEventRepository(EventRepository):
        def add_in_transaction(self, connection, event):
            raise RuntimeError("injected event failure")

    service = AttemptSubmissionService(
        LearningRecordRepository(
            database,
            attempts,
            FailingEventRepository(database, cipher),
        )
    )
    command = SubmitAttemptCommand(
        user_id=user.id,
        exercise_id=exercise.id,
        source_code="print(3)",
        duration_ms=3,
    )

    with pytest.raises(RuntimeError, match="injected"):
        service.submit(command)

    assert attempts.list_for_user(user.id) == ()

