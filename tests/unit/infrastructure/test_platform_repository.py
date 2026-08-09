"""Persistence tests for private diagnostics and controlled rollout."""

from aprendix.application.contracts import (
    BaselineMetricDTO,
    DiagnosticEventDTO,
    DiagnosticSeverity,
)
from aprendix.infrastructure.db import PlatformRepository


def test_feature_flags_are_seeded_and_overrides_are_persisted(database, cipher) -> None:
    repository = PlatformRepository(database, cipher)
    repository.seed_feature_flags()

    assert repository.feature_enabled("ide.debugger") is True
    changed = repository.set_feature("ide.debugger", True)

    assert changed.enabled is True
    assert changed.source == "override"
    assert repository.feature_enabled("ide.debugger") is True
    assert len(repository.feature_flags()) >= 14


def test_diagnostic_context_is_encrypted_at_rest(database, cipher) -> None:
    repository = PlatformRepository(database, cipher)
    event = DiagnosticEventDTO(
        code="runtime.startup", severity=DiagnosticSeverity.INFO,
        subsystem="runtime", message="Arranque concluído.",
        context={"duration_ms": 12.5, "status": "ok"},
    )
    repository.record_diagnostic(event)

    with database.read_connection() as connection:
        stored = connection.execute(
            "SELECT context_encrypted FROM diagnostic_events WHERE id=?", (str(event.id),)
        ).fetchone()[0]
    assert b"duration_ms" not in stored
    restored = repository.diagnostics(limit=1)[0]
    assert restored.context == event.context
    assert restored.message == "Arranque concluído."


def test_baseline_metric_round_trip(database, cipher) -> None:
    repository = PlatformRepository(database, cipher)
    metric = BaselineMetricDTO(
        name="runtime.startup", value=321.25, unit="ms",
        context={"schema_version": 15},
    )
    repository.record_metric(metric)

    assert repository.metrics("runtime.startup") == (metric,)
