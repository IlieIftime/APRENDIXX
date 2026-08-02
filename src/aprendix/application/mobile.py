"""Mobile-oriented structural completion, focus timing, and anti-copy policy."""

from __future__ import annotations

import hashlib
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum, StrEnum

from pydantic import BaseModel, ConfigDict, Field


class CompletionSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    insert_text: str
    display_text: str
    confidence: float = Field(ge=0.0, le=1.0)
    structural_reason: str


class StructuralCompletionEngine:
    """Suggest Python syntax only; never infer business identifiers or answers."""

    _KEYWORDS = (
        "def",
        "class",
        "if",
        "elif",
        "else",
        "for",
        "while",
        "return",
        "try",
        "except",
        "with",
        "import",
        "from",
    )

    def suggest(
        self,
        source: str,
        cursor: int,
        *,
        proficiency: float,
    ) -> tuple[CompletionSuggestion, ...]:
        if not 0.0 <= proficiency <= 1.0:
            raise ValueError("proficiency must be between 0 and 1")
        if not 0 <= cursor <= len(source):
            raise ValueError("cursor is outside source")

        before = source[:cursor]
        current_line = before.rsplit("\n", 1)[-1]
        suggestions: list[CompletionSuggestion] = []

        function_match = re.fullmatch(r"(\s*)def\s+([A-Za-z_]\w*)", current_line)
        if function_match:
            suggestions.append(
                CompletionSuggestion(
                    insert_text="():\n" + function_match.group(1) + "    ",
                    display_text="():",
                    confidence=0.99,
                    structural_reason="complete function signature",
                )
            )
        elif re.fullmatch(
            r"\s*(?:if|elif|else|for|while|try|except|with)\b[^:\n]*",
            current_line,
        ):
            suggestions.append(
                CompletionSuggestion(
                    insert_text=":\n" + re.match(r"\s*", current_line).group(0) + "    ",
                    display_text=":",
                    confidence=0.96,
                    structural_reason="open an indented Python block",
                )
            )

        token_match = re.search(r"([A-Za-z]+)$", before)
        if token_match:
            prefix = token_match.group(1)
            for keyword in self._KEYWORDS:
                if keyword.startswith(prefix) and keyword != prefix:
                    suggestions.append(
                        CompletionSuggestion(
                            insert_text=keyword[len(prefix) :] + " ",
                            display_text=keyword,
                            confidence=0.9 - (len(keyword) - len(prefix)) * 0.02,
                            structural_reason="complete a Python structural keyword",
                        )
                    )

        # Novices see up to three structural options; advanced learners see one.
        allowance = max(1, math.ceil((1.0 - proficiency) * 3))
        ordered = sorted(
            suggestions,
            key=lambda item: (-item.confidence, item.display_text),
        )
        return tuple(ordered[:allowance])

    @staticmethod
    def apply(source: str, cursor: int, suggestion: CompletionSuggestion) -> str:
        if not 0 <= cursor <= len(source):
            raise ValueError("cursor is outside source")
        return source[:cursor] + suggestion.insert_text + source[cursor:]


class FocusMinutes(IntEnum):
    SHORT = 25
    STANDARD = 50
    DEEP = 90
    EXTENDED = 120


class TimerState(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"


class PomodoroTimer:
    """A monotonic, sleep-free focus timer suitable for GUI event loops."""

    def __init__(
        self,
        mode: FocusMinutes = FocusMinutes.SHORT,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._duration = int(mode) * 60.0
        self._clock = clock
        self._state = TimerState.IDLE
        self._started_at: float | None = None
        self._elapsed_before_start = 0.0

    @property
    def state(self) -> TimerState:
        self._refresh()
        return self._state

    def start(self) -> None:
        if self._state not in {TimerState.IDLE, TimerState.PAUSED}:
            raise RuntimeError(f"cannot start timer in state {self._state}")
        self._started_at = self._clock()
        self._state = TimerState.RUNNING

    def pause(self) -> None:
        if self._state is not TimerState.RUNNING:
            raise RuntimeError("only a running timer can be paused")
        self._elapsed_before_start = self.elapsed_seconds()
        self._started_at = None
        self._state = TimerState.PAUSED

    def reset(self) -> None:
        self._state = TimerState.IDLE
        self._started_at = None
        self._elapsed_before_start = 0.0

    def elapsed_seconds(self) -> float:
        elapsed = self._elapsed_before_start
        if self._state is TimerState.RUNNING and self._started_at is not None:
            elapsed += max(0.0, self._clock() - self._started_at)
        return min(self._duration, elapsed)

    def remaining_seconds(self) -> float:
        self._refresh()
        return max(0.0, self._duration - self.elapsed_seconds())

    def _refresh(self) -> None:
        if (
            self._state is TimerState.RUNNING
            and self.elapsed_seconds() >= self._duration
        ):
            self._elapsed_before_start = self._duration
            self._started_at = None
            self._state = TimerState.COMPLETED


@dataclass(frozen=True, slots=True)
class EditTelemetry:
    typed_characters: int
    pasted_characters: int
    deleted_characters: int = 0

    def __post_init__(self) -> None:
        if min(
            self.typed_characters,
            self.pasted_characters,
            self.deleted_characters,
        ) < 0:
            raise ValueError("edit counters cannot be negative")

    @property
    def paste_ratio(self) -> float:
        total = self.typed_characters + self.pasted_characters
        return self.pasted_characters / total if total else 0.0


class AntiCopyDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    requires_justification: bool
    paste_ratio: float = Field(ge=0.0, le=1.0)
    reason: str
    prompt_variant: str


class CodeProvenanceGuard:
    """Apply proportionate friction without blocking legitimate accessibility."""

    _PREFIXES = (
        "Explica por etapas:",
        "Justifica as decisões principais:",
        "Mostra o teu raciocínio estrutural:",
    )

    def assess(
        self,
        telemetry: EditTelemetry,
        *,
        proficiency: float,
        prompt: str,
        exercise_id: str,
    ) -> AntiCopyDecision:
        if not 0.0 <= proficiency <= 1.0:
            raise ValueError("proficiency must be between 0 and 1")
        threshold = 0.75 - 0.25 * proficiency
        requires = (
            telemetry.pasted_characters >= 40
            and telemetry.paste_ratio > threshold
        )
        prefix_index = int.from_bytes(
            hashlib.sha256(exercise_id.encode("utf-8")).digest()[:2],
            "big",
        ) % len(self._PREFIXES)
        variant = f"{self._PREFIXES[prefix_index]} {prompt.strip()}"
        reason = (
            "large paste ratio requires a short conceptual explanation"
            if requires
            else "editing pattern is consistent with active construction"
        )
        return AntiCopyDecision(
            requires_justification=requires,
            paste_ratio=telemetry.paste_ratio,
            reason=reason,
            prompt_variant=variant,
        )

    @staticmethod
    def validate_justification(text: str) -> bool:
        words = re.findall(r"[A-Za-zÀ-ÿ0-9]+", text)
        unique = {word.casefold() for word in words}
        return len(words) >= 8 and len(unique) >= 5

