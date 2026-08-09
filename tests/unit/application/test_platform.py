"""Application tests for health and privacy-safe operational metadata."""

from pathlib import Path

from aprendix.application.contracts import DiagnosticSeverity, HealthStatus
from aprendix.application.platform import PlatformService
from aprendix.infrastructure.db.schema import SCHEMA_VERSION
from aprendix.infrastructure.db import PlatformRepository


def test_platform_health_checks_local_components(database, cipher, tmp_path: Path) -> None:
    data = tmp_path / "data"
    (data / "keys").mkdir(parents=True)
    (data / "keys" / "fields.key").write_bytes(b"x" * 32)
    (data / "cache").mkdir()
    repository = PlatformRepository(database, cipher)
    repository.seed_feature_flags()
    service = PlatformService(
        repository=repository, database=database, data_directory=data,
        expected_schema_version=SCHEMA_VERSION,
    )

    health = service.health()

    assert health.status is HealthStatus.HEALTHY
    assert health.component_map["database"].status is HealthStatus.HEALTHY
    assert health.component_map["foreign-keys"].detail == "violations=0"
    assert health.component_map["sandbox"].detail == "deep-check-not-requested"


def test_diagnostics_drop_private_or_unbounded_context(database, cipher, tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    repository = PlatformRepository(database, cipher)
    service = PlatformService(
        repository=repository, database=database, data_directory=data,
        expected_schema_version=15,
    )

    event = service.diagnose(
        code="search.failed", severity=DiagnosticSeverity.WARNING,
        subsystem="search", message="Pesquisa indisponível.",
        context={
            "operation": "hybrid", "error_type": "TimeoutError",
            "query": "segredo do utilizador", "source_code": "print('privado')",
            "path": "C:/Users/private/file.py", "nested": {"secret": True},
        },
    )

    assert event.context == {"operation": "hybrid", "error_type": "TimeoutError"}
    assert repository.diagnostics(limit=1)[0].context == event.context


def test_metric_context_uses_same_privacy_filter(database, cipher, tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    repository = PlatformRepository(database, cipher)
    service = PlatformService(
        repository=repository, database=database, data_directory=data,
        expected_schema_version=15,
    )

    metric = service.record_metric(
        "search.latency", 42.0, "ms",
        context={"result_count": 3, "query": "não guardar"},
    )

    assert metric.context == {"result_count": 3}
    assert service.metrics("search.latency") == (metric,)
