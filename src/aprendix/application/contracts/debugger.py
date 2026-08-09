"""Strict contracts for isolated, deterministic Python debugging."""

from __future__ import annotations

from typing import Literal

from pydantic import ConfigDict, Field, field_validator

from aprendix.application.contracts.models import ContractModel
from aprendix.application.contracts.copykate import SourceCode


class DebugBreakpointDTO(ContractModel):
    line: int = Field(ge=1, le=100_000)
    condition: str = Field(default="", max_length=500)


class DebugRequestDTO(ContractModel):
    model_config = ConfigDict(str_strip_whitespace=False)
    source_code: SourceCode
    breakpoints: tuple[DebugBreakpointDTO, ...] = Field(default=(), max_length=100)
    watches: tuple[str, ...] = Field(default=(), max_length=30)
    stdin: tuple[str, ...] = Field(default=(), max_length=100)
    timeout_ms: int = Field(default=3_000, ge=100, le=10_000)
    memory_limit_mb: int = Field(default=192, ge=64, le=512)
    max_output_bytes: int = Field(default=32_768, ge=128, le=262_144)
    max_steps: int = Field(default=2_000, ge=1, le=20_000)

    @field_validator("watches")
    @classmethod
    def watches_are_non_blank(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(item.strip() for item in value if item.strip())
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("debug watches must be unique")
        return cleaned


class DebugFrameDTO(ContractModel):
    step: int = Field(ge=1)
    line: int = Field(ge=1)
    event: Literal["call", "line", "return", "exception"]
    function: str = Field(max_length=200)
    call_depth: int = Field(ge=0, le=200)
    locals: dict[str, str] = Field(default_factory=dict)
    globals: dict[str, str] = Field(default_factory=dict)
    watches: dict[str, str] = Field(default_factory=dict)
    stdout: str = Field(default="", max_length=262_144)
    breakpoint_hit: bool = False


class DebugSessionDTO(ContractModel):
    status: Literal[
        "completed", "runtime_error", "timeout", "step_limit", "rejected",
        "infrastructure_error", "output_limit",
    ]
    frames: tuple[DebugFrameDTO, ...] = Field(default=(), max_length=20_000)
    stdout: str = Field(default="", max_length=262_144)
    duration_ms: int = Field(ge=0)
    coverage_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    executed_lines: tuple[int, ...] = Field(default=())
    error_type: str | None = Field(default=None, max_length=200)
    error_message: str | None = Field(default=None, max_length=2_000)
    token_verified: bool = False
    memory_limit_enforced: bool = False
