"""Application-owned ports implemented by infrastructure adapters."""

from __future__ import annotations

from typing import Protocol

from aprendix.application.contracts import AttemptDTO, EventDTO, ExerciseDTO


class EventSink(Protocol):
    def append(self, event: EventDTO) -> bool:
        """Persist an event, returning false for an identical replay."""


class SubmissionStore(Protocol):
    def record(self, attempt: AttemptDTO, event: EventDTO) -> bool:
        """Atomically persist an attempt and its corresponding event."""


class ExerciseCatalog(Protocol):
    def list_all(self) -> tuple[ExerciseDTO, ...]:
        """Return the locally available exercises in deterministic order."""


class EventObserver(Protocol):
    def update_node_stats(self, event: EventDTO) -> object:
        """Project one immutable event into a derived local read model."""
