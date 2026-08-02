"""Scripted CLI tests without terminal or network dependencies."""

from collections.abc import Iterator
from unittest.mock import Mock

from aprendix.application.contracts import UserDTO
from aprendix.application.services import AttemptSubmissionService, EventIngestionService
from aprendix.infrastructure.db import (
    AttemptRepository,
    Database,
    EventRepository,
    ExerciseRepository,
    LearningRecordRepository,
    UserRepository,
)
from aprendix.infrastructure.security import AesGcmFieldCipher
from aprendix.infrastructure.seed import seed_default_catalog
from aprendix.presentation.cli import run_cli


def scripted_input(values: list[str]) -> Mock:
    iterator: Iterator[str] = iter(values)
    return Mock(side_effect=lambda _prompt="": next(iterator))


def test_cli_happy_path_persists_attempt_and_events(
    database: Database,
    cipher: AesGcmFieldCipher,
) -> None:
    seed_default_catalog(database)
    user = UserDTO(display_name="CLI user")
    UserRepository(database, cipher).add(user)
    event_repository = EventRepository(database, cipher)
    attempt_repository = AttemptRepository(database, cipher)
    output = Mock()

    result = run_cli(
        user=user,
        exercises=ExerciseRepository(database, cipher),
        events=EventIngestionService(event_repository),
        submissions=AttemptSubmissionService(
            LearningRecordRepository(
                database,
                attempt_repository,
                event_repository,
            )
        ),
        input_fn=scripted_input(["1", "print('Olá')", "END", "0"]),
        output_fn=output,
        clock=Mock(side_effect=[10.0, 11.25]),
    )

    assert result == 0
    assert len(attempt_repository.list_for_user(user.id)) == 1
    assert len(event_repository.list_for_user(user.id)) == 2
    rendered = "\n".join(call.args[0] for call in output.call_args_list)
    assert "Tentativa guardada localmente" in rendered
    assert "Até breve" in rendered


def test_cli_reprompts_invalid_choice_and_drops_blank_attempt(
    database: Database,
    cipher: AesGcmFieldCipher,
) -> None:
    seed_default_catalog(database)
    user = UserDTO()
    UserRepository(database, cipher).add(user)
    event_repository = EventRepository(database, cipher)
    attempt_repository = AttemptRepository(database, cipher)
    output = Mock()

    result = run_cli(
        user=user,
        exercises=ExerciseRepository(database, cipher),
        events=EventIngestionService(event_repository),
        submissions=AttemptSubmissionService(
            LearningRecordRepository(
                database,
                attempt_repository,
                event_repository,
            )
        ),
        input_fn=scripted_input(["banana", "9", "1", "  ", "END", "0"]),
        output_fn=output,
        clock=Mock(side_effect=[1.0]),
    )

    assert result == 0
    assert attempt_repository.list_for_user(user.id) == ()
    rendered = "\n".join(call.args[0] for call in output.call_args_list)
    assert rendered.count("Opção inválida") == 2
    assert "tentativa vazia" in rendered


def test_cli_treats_learner_source_as_inert_text(
    database: Database,
    cipher: AesGcmFieldCipher,
    tmp_path,
) -> None:
    seed_default_catalog(database)
    user = UserDTO()
    UserRepository(database, cipher).add(user)
    events = EventRepository(database, cipher)
    attempts = AttemptRepository(database, cipher)
    target = tmp_path / "must-not-exist.txt"
    dangerous_text = f"__import__('pathlib').Path(r'{target}').write_text('bad')"

    run_cli(
        user=user,
        exercises=ExerciseRepository(database, cipher),
        events=EventIngestionService(events),
        submissions=AttemptSubmissionService(
            LearningRecordRepository(database, attempts, events)
        ),
        input_fn=scripted_input(["1", dangerous_text, "END", "0"]),
        output_fn=Mock(),
        clock=Mock(side_effect=[2.0, 2.1]),
    )

    assert not target.exists()
    assert attempts.list_for_user(user.id)[0].source_code == dangerous_text


def test_cli_exits_cleanly_on_eof(
    database: Database,
    cipher: AesGcmFieldCipher,
) -> None:
    seed_default_catalog(database)
    user = UserDTO()
    UserRepository(database, cipher).add(user)
    events = EventRepository(database, cipher)
    output = Mock()

    result = run_cli(
        user=user,
        exercises=ExerciseRepository(database, cipher),
        events=EventIngestionService(events),
        submissions=AttemptSubmissionService(
            LearningRecordRepository(
                database,
                AttemptRepository(database, cipher),
                events,
            )
        ),
        input_fn=Mock(side_effect=EOFError),
        output_fn=output,
    )

    assert result == 0
    assert events.list_for_user(user.id) == ()
