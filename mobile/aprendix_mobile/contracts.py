"""Small pure-Python contracts for the native mobile runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID, uuid4


class SnippetAction(str, Enum):
    EXPLAIN = "explain"
    COMPLETE = "complete"
    TO_ALGORITHM = "to_algorithm"
    TO_PYTHON = "to_python"
    FIND_PROBLEMS = "find_problems"
    CREATE_TESTS = "create_tests"
    VISUALIZE = "visualize"
    LINK_COURSE = "link_course"


@dataclass(frozen=True, slots=True)
class OcrRegionDTO:
    text: str
    confidence: float
    box: tuple[tuple[int, int], ...] = ()
    ambiguous: bool = False


@dataclass(frozen=True, slots=True)
class OcrDraftDTO:
    text: str
    confidence: float
    regions: tuple[OcrRegionDTO, ...] = ()
    warnings: tuple[str, ...] = ()
    requires_confirmation: bool = True


@dataclass(frozen=True, slots=True)
class SnippetRequestDTO:
    text: str
    language_hint: str = "auto"
    action: SnippetAction = SnippetAction.EXPLAIN
    ocr_confirmed: bool = False

    def __post_init__(self) -> None:
        if not self.text.strip() or len(self.text) > 100_000:
            raise ValueError("O trecho deve conter entre 1 e 100000 caracteres.")
        if self.language_hint not in {"auto", "python", "pseudocode"}:
            raise ValueError("Linguagem inválida.")


@dataclass(frozen=True, slots=True)
class SnippetAnalysisDTO:
    original: str
    normalized: str
    detected_language: str
    summary: str
    complexity_time: str
    complexity_space: str
    id: UUID = field(default_factory=uuid4)
    line_explanations: tuple[str, ...] = ()
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    invariants: tuple[str, ...] = ()
    constructs: tuple[str, ...] = ()
    control_flow: tuple[tuple[str, str], ...] = ()
    problems: tuple[str, ...] = ()
    suggested_tests: tuple[str, ...] = ()
    proposed_code: str = ""
    related_concepts: tuple[str, ...] = ()
    confidence: float = 0.0
