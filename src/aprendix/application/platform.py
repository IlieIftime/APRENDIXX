"""Runtime health, private diagnostics, and controlled feature rollout."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, Callable

from aprendix.application.contracts import (
    BaselineMetricDTO,
    ComponentHealthDTO,
    DiagnosticEventDTO,
    DiagnosticSeverity,
    HealthStatus,
    RuntimeHealthDTO,
    SandboxRequest,
    sanitize_diagnostic_context,
)
class PlatformService:
    def __init__(self, *, repository, database, data_directory: Path,
                 expected_schema_version: int,
                 sandbox_runner: Callable[[SandboxRequest], Any] | None = None) -> None:
        self._repository = repository
        self._database = database
        self._data_directory = data_directory.resolve()
        self._expected_schema_version = expected_schema_version
        self._sandbox_runner = sandbox_runner

    def feature_enabled(self, name: str, *, default: bool = False) -> bool:
        return self._repository.feature_enabled(name, default=default)

    def set_feature(self, name: str, enabled: bool):
        return self._repository.set_feature(name, enabled)

    def feature_flags(self):
        return self._repository.feature_flags()

    def record_metric(self, name: str, value: float, unit: str,
                      *, context: dict[str, Any] | None = None) -> BaselineMetricDTO:
        metric = BaselineMetricDTO(
            name=name, value=value, unit=unit,
            context=sanitize_diagnostic_context(context or {}),
        )
        self._repository.record_metric(metric)
        return metric

    def metrics(self, name: str, *, limit: int = 30):
        return self._repository.metrics(name, limit=limit)

    def diagnose(self, *, code: str, severity: DiagnosticSeverity,
                 subsystem: str, message: str,
                 context: dict[str, Any] | None = None) -> DiagnosticEventDTO:
        event = DiagnosticEventDTO(
            code=code, severity=severity, subsystem=subsystem, message=message,
            context=sanitize_diagnostic_context(context or {}),
        )
        self._repository.record_diagnostic(event)
        return event

    def diagnostics(self, *, limit: int = 100):
        return self._repository.diagnostics(limit=limit)

    @staticmethod
    def _component(component: str, status: HealthStatus, detail: str,
                   started: float) -> ComponentHealthDTO:
        return ComponentHealthDTO(
            component=component, status=status, detail=detail,
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
        )

    def health(self, *, deep: bool = False) -> RuntimeHealthDTO:
        components: list[ComponentHealthDTO] = []

        started = time.perf_counter()
        try:
            with self._database.read_connection() as connection:
                integrity = connection.execute("PRAGMA quick_check").fetchone()[0]
                schema = int(connection.execute(
                    "SELECT COALESCE(max(version),0) FROM schema_migrations"
                ).fetchone()[0])
            status = HealthStatus.HEALTHY if integrity == "ok" and schema == self._expected_schema_version else HealthStatus.FAILED
            components.append(self._component("database", status, f"integrity={integrity}; schema={schema}", started))
        except Exception as exc:
            components.append(self._component("database", HealthStatus.FAILED, f"{type(exc).__name__}", started))

        started = time.perf_counter()
        try:
            with self._database.read_connection() as connection:
                violations = len(connection.execute("PRAGMA foreign_key_check").fetchall())
            status = HealthStatus.HEALTHY if violations == 0 else HealthStatus.FAILED
            components.append(self._component("foreign-keys", status, f"violations={violations}", started))
        except Exception as exc:
            components.append(self._component("foreign-keys", HealthStatus.FAILED, type(exc).__name__, started))

        started = time.perf_counter()
        try:
            with self._database.read_connection() as connection:
                accepted = int(connection.execute(
                    "SELECT count(*) FROM chunk_quality WHERE status='accepted'"
                ).fetchone()[0])
                quarantined = int(connection.execute(
                    "SELECT count(*) FROM chunk_quality WHERE status='quarantined'"
                ).fetchone()[0])
            components.append(self._component(
                "knowledge", HealthStatus.HEALTHY,
                f"accepted={accepted}; quarantined={quarantined}", started,
            ))
        except Exception as exc:
            components.append(self._component("knowledge", HealthStatus.FAILED, type(exc).__name__, started))

        started = time.perf_counter()
        key_path = self._data_directory / "keys" / "fields.key"
        key_ok = key_path.is_file() and key_path.stat().st_size == 32
        components.append(self._component(
            "key-store", HealthStatus.HEALTHY if key_ok else HealthStatus.FAILED,
            "available" if key_ok else "missing-or-invalid", started,
        ))

        started = time.perf_counter()
        cache_path = self._data_directory / "cache"
        cache_ok = cache_path.is_dir()
        components.append(self._component(
            "cache", HealthStatus.HEALTHY if cache_ok else HealthStatus.DEGRADED,
            "available" if cache_ok else "directory-missing", started,
        ))

        started = time.perf_counter()
        try:
            free = shutil.disk_usage(self._data_directory).free
            disk_status = HealthStatus.HEALTHY if free >= 512 * 1024 * 1024 else HealthStatus.DEGRADED
            components.append(self._component("storage", disk_status, f"available_bytes={free}", started))
        except OSError as exc:
            components.append(self._component("storage", HealthStatus.DEGRADED, type(exc).__name__, started))

        started = time.perf_counter()
        if deep and self._sandbox_runner is not None:
            try:
                result = self._sandbox_runner(SandboxRequest(
                    source_code="print(6 * 7)", timeout_ms=2_000,
                    memory_limit_mb=128, max_output_bytes=1024,
                ))
                sandbox_ok = result.status == "ok" and result.stdout.strip() == "42"
                components.append(self._component(
                    "sandbox", HealthStatus.HEALTHY if sandbox_ok else HealthStatus.FAILED,
                    f"status={result.status}", started,
                ))
            except Exception as exc:
                components.append(self._component("sandbox", HealthStatus.FAILED, type(exc).__name__, started))
        else:
            components.append(self._component("sandbox", HealthStatus.HEALTHY, "deep-check-not-requested", started))

        statuses = {item.status for item in components}
        overall = (
            HealthStatus.FAILED if HealthStatus.FAILED in statuses else
            HealthStatus.DEGRADED if HealthStatus.DEGRADED in statuses else
            HealthStatus.HEALTHY
        )
        return RuntimeHealthDTO(
            status=overall, schema_version=self._expected_schema_version, components=tuple(components)
        )
