"""Interactive local CLI for the Sprint 2 learning flow."""

from __future__ import annotations

import time
from collections.abc import Callable
from uuid import uuid4

from aprendix.application.contracts import EventDTO, SubmitAttemptCommand, UserDTO
from aprendix.application.ports import ExerciseCatalog
from aprendix.application.services import (
    AttemptSubmissionService,
    EventIngestionService,
)
from aprendix.domain import EventType

InputFn = Callable[[str], str]
OutputFn = Callable[[str], None]
ClockFn = Callable[[], float]

def read_source(input_fn: InputFn, output_fn: OutputFn) -> str:
    output_fn("Introduz o código. Termina com uma linha contendo apenas END.")
    lines: list[str] = []
    while True:
        line = input_fn("")
        if line == "END":
            break
        lines.append(line)
    return "\n".join(lines)


def run_cli(
    *,
    user: UserDTO,
    exercises: ExerciseCatalog,
    events: EventIngestionService,
    submissions: AttemptSubmissionService,
    input_fn: InputFn = input,
    output_fn: OutputFn = print,
    clock: ClockFn = time.monotonic,
) -> int:
    """Run a testable menu loop without network or code execution."""

    output_fn("Aprendix — prática primeiro, totalmente local.")
    while True:
        catalogue = exercises.list_all()
        output_fn("\nExercícios:")
        for index, exercise in enumerate(catalogue, start=1):
            output_fn(f"{index}. {exercise.title}")
        output_fn("0. Sair")

        try:
            choice = input_fn("Escolhe um exercício: ").strip()
        except EOFError:
            output_fn("\nEntrada terminada. Até breve!")
            return 0
        except KeyboardInterrupt:
            output_fn("\nSessão interrompida.")
            return 130
        if choice == "0":
            output_fn("Até breve!")
            return 0
        if not choice.isdigit() or not 1 <= int(choice) <= len(catalogue):
            output_fn("Opção inválida.")
            continue

        exercise = catalogue[int(choice) - 1]
        events.ingest(
            EventDTO(
                idempotency_key=uuid4(),
                user_id=user.id,
                event_type=EventType.EXERCISE_OPENED,
                payload={"exercise_id": str(exercise.id)},
            )
        )
        output_fn(f"\n{exercise.title}\n{exercise.prompt}")
        if exercise.starter_code:
            output_fn(f"\nCódigo inicial:\n{exercise.starter_code}")

        started = clock()
        try:
            source_code = read_source(input_fn, output_fn)
        except EOFError:
            output_fn("Entrada terminada; tentativa cancelada.")
            return 0
        except KeyboardInterrupt:
            output_fn("\nTentativa cancelada.")
            return 130
        if not source_code.strip():
            output_fn("A tentativa vazia não foi guardada.")
            continue

        duration_ms = max(0, round((clock() - started) * 1_000))
        receipt = submissions.submit(
            SubmitAttemptCommand(
                user_id=user.id,
                exercise_id=exercise.id,
                source_code=source_code,
                duration_ms=duration_ms,
            )
        )
        output_fn(f"Tentativa guardada localmente: {receipt.attempt_id}")
