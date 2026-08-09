"""Strict contracts for local text/image snippet assistance."""

from __future__ import annotations

from enum import Enum
from uuid import UUID, uuid4

from pydantic import ConfigDict, Field

from aprendix.application.contracts.models import ContractModel, NonBlankText


class SnippetAction(str, Enum):
    EXPLAIN = "explain"
    COMPLETE = "complete"
    TO_ALGORITHM = "to_algorithm"
    TO_PYTHON = "to_python"
    FIND_PROBLEMS = "find_problems"
    CREATE_TESTS = "create_tests"
    VISUALIZE = "visualize"
    LINK_COURSE = "link_course"


class OcrRegionDTO(ContractModel):
    text: str = Field(max_length=20_000)
    confidence: float = Field(ge=0.0, le=1.0)
    box: tuple[tuple[int, int], ...] = Field(default=(), max_length=8)
    ambiguous: bool = False


class OcrDraftDTO(ContractModel):
    text: str = Field(max_length=100_000)
    confidence: float = Field(ge=0.0, le=1.0)
    regions: tuple[OcrRegionDTO, ...] = Field(default=(), max_length=2_000)
    warnings: tuple[str, ...] = Field(default=(), max_length=100)
    requires_confirmation: bool = True


class SnippetRequestDTO(ContractModel):
    model_config = ConfigDict(str_strip_whitespace=False)
    text: NonBlankText = Field(max_length=100_000)
    language_hint: str = Field(default="auto", pattern=r"^(auto|python|pseudocode)$")
    action: SnippetAction = SnippetAction.EXPLAIN
    ocr_confirmed: bool = False


class SnippetAnalysisDTO(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    original: NonBlankText = Field(max_length=100_000)
    normalized: NonBlankText = Field(max_length=100_000)
    detected_language: str = Field(pattern=r"^(python|pseudocode|text)$")
    summary: NonBlankText = Field(max_length=10_000)
    line_explanations: tuple[str, ...] = Field(default=(), max_length=2_000)
    inputs: tuple[str, ...] = Field(default=(), max_length=100)
    outputs: tuple[str, ...] = Field(default=(), max_length=100)
    invariants: tuple[str, ...] = Field(default=(), max_length=100)
    constructs: tuple[str, ...] = Field(default=(), max_length=100)
    control_flow: tuple[tuple[str, str], ...] = Field(default=(), max_length=5_000)
    complexity_time: str = Field(max_length=80)
    complexity_space: str = Field(max_length=80)
    problems: tuple[str, ...] = Field(default=(), max_length=100)
    suggested_tests: tuple[str, ...] = Field(default=(), max_length=100)
    proposed_code: str = Field(default="", max_length=100_000)
    related_concepts: tuple[str, ...] = Field(default=(), max_length=100)
    confidence: float = Field(ge=0.0, le=1.0)
