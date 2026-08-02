"""Sprint 7 structural completion, focus, and anti-copy tests."""

import pytest

from aprendix.application.mobile import (
    CodeProvenanceGuard,
    EditTelemetry,
    FocusMinutes,
    PomodoroTimer,
    StructuralCompletionEngine,
    TimerState,
)


def test_completion_finishes_function_signature_and_indentation() -> None:
    engine = StructuralCompletionEngine()

    suggestions = engine.suggest("def soma", 8, proficiency=0.1)
    completed = engine.apply("def soma", 8, suggestions[0])

    assert completed == "def soma():\n    "
    assert all("soma" not in item.insert_text for item in suggestions)


def test_completion_help_decreases_with_proficiency() -> None:
    engine = StructuralCompletionEngine()

    novice = engine.suggest("e", 1, proficiency=0.0)
    advanced = engine.suggest("e", 1, proficiency=1.0)

    assert len(novice) > len(advanced)
    assert {item.display_text for item in novice} <= {"elif", "else", "except"}


def test_pomodoro_uses_monotonic_clock_without_sleeping() -> None:
    now = [10.0]
    timer = PomodoroTimer(FocusMinutes.SHORT, clock=lambda: now[0])

    timer.start()
    now[0] = 1510.0

    assert timer.remaining_seconds() == 0
    assert timer.state is TimerState.COMPLETED


def test_pomodoro_pause_and_reset() -> None:
    now = [1.0]
    timer = PomodoroTimer(FocusMinutes.STANDARD, clock=lambda: now[0])
    timer.start()
    now[0] = 11.0
    timer.pause()

    assert timer.state is TimerState.PAUSED
    assert timer.elapsed_seconds() == 10
    timer.reset()
    assert timer.state is TimerState.IDLE


def test_anti_copy_requires_explanation_for_large_paste() -> None:
    guard = CodeProvenanceGuard()
    telemetry = EditTelemetry(typed_characters=10, pasted_characters=90)

    decision = guard.assess(
        telemetry,
        proficiency=0.8,
        prompt="Resolve o exercício.",
        exercise_id="abc",
    )

    assert decision.requires_justification is True
    assert decision.prompt_variant.endswith("Resolve o exercício.")
    assert guard.validate_justification(
        "Usei uma condição para separar claramente os dois casos possíveis."
    )
    assert not guard.validate_justification("porque sim")


def test_mobile_services_reject_invalid_ranges() -> None:
    with pytest.raises(ValueError):
        StructuralCompletionEngine().suggest("", 0, proficiency=2.0)
    with pytest.raises(ValueError):
        EditTelemetry(-1, 0)
