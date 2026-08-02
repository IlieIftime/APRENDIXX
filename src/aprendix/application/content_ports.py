"""Optional ports used by the Sprint 4 content orchestrator."""

from __future__ import annotations

from typing import Protocol

from aprendix.application.contracts.content import (
    NLPHintRequestDTO,
    NLPHintResponseDTO,
)


class NLPUnavailableError(RuntimeError):
    """Raised when the local quantized model cannot serve a request."""


class QuantizedNLPAdapter(Protocol):
    """Boundary for an optional, bounded-latency on-device hint model."""

    def generate_hints(
        self,
        request: NLPHintRequestDTO,
        *,
        timeout_seconds: float,
    ) -> NLPHintResponseDTO:
        """Return validated hint text or raise when unavailable within the budget."""
