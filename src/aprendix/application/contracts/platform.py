"""Contracts for local diagnostics, feature rollout, and runtime health."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import Field
from pydantic.types import JsonValue

from aprendix.application.contracts.models import ContractModel, NonBlankText, utc_now


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


class DiagnosticSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class FeatureFlagDTO(ContractModel):
    name: NonBlankText = Field(max_length=100, pattern=r"^[a-z][a-z0-9_.-]+$")
    enabled: bool = False
    source: str = Field(default="default", pattern=r"^(default|override|migration)$")
    updated_at: datetime = Field(default_factory=utc_now)


class DiagnosticEventDTO(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    code: NonBlankText = Field(max_length=100, pattern=r"^[a-z][a-z0-9_.-]+$")
    severity: DiagnosticSeverity
    subsystem: NonBlankText = Field(max_length=60, pattern=r"^[a-z][a-z0-9_.-]+$")
    message: NonBlankText = Field(max_length=240)
    context: dict[str, JsonValue] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=utc_now)


class BaselineMetricDTO(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    name: NonBlankText = Field(max_length=100, pattern=r"^[a-z][a-z0-9_.-]+$")
    value: float
    unit: NonBlankText = Field(max_length=24, pattern=r"^[a-z][a-z0-9_.%/-]+$")
    context: dict[str, JsonValue] = Field(default_factory=dict)
    measured_at: datetime = Field(default_factory=utc_now)


class ComponentHealthDTO(ContractModel):
    component: NonBlankText = Field(max_length=60)
    status: HealthStatus
    detail: NonBlankText = Field(max_length=240)
    duration_ms: float = Field(default=0.0, ge=0.0)


class RuntimeHealthDTO(ContractModel):
    status: HealthStatus
    schema_version: int = Field(ge=1)
    components: tuple[ComponentHealthDTO, ...]
    generated_at: datetime = Field(default_factory=utc_now)

    @property
    def component_map(self) -> dict[str, ComponentHealthDTO]:
        return {item.component: item for item in self.components}


SafeDiagnosticValue = str | int | float | bool | None


def sanitize_diagnostic_context(context: dict[str, Any]) -> dict[str, SafeDiagnosticValue]:
    """Keep operational metadata while dropping code, paths, queries, and user text."""

    allowed = {
        "component", "operation", "error_type", "status", "duration_ms",
        "count", "version", "path_kind", "feature", "schema_version",
        "bytes", "available_bytes", "result_count", "mode",
    }
    result: dict[str, SafeDiagnosticValue] = {}
    for key, value in context.items():
        normalized = str(key).strip().lower()
        if normalized not in allowed or not isinstance(value, (str, int, float, bool, type(None))):
            continue
        if isinstance(value, str):
            value = value[:160]
        result[normalized] = value
    return result
