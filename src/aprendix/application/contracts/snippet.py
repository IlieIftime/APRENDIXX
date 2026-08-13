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


class SnippetDiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFORMATION = "information"


class DiagnosticDTO(ContractModel):
    """One location-aware, evidence-backed static-analysis diagnostic."""

    code: NonBlankText = Field(max_length=120)
    severity: SnippetDiagnosticSeverity
    line: int = Field(ge=1, le=1_000_000)
    column: int = Field(default=0, ge=0, le=1_000_000)
    end_line: int | None = Field(default=None, ge=1, le=1_000_000)
    end_column: int | None = Field(default=None, ge=0, le=1_000_000)
    message: NonBlankText = Field(max_length=2_000)
    evidence: str = Field(default="", max_length=2_000)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    safe_fix: str = Field(default="", max_length=2_000)


class SymbolDTO(ContractModel):
    name: NonBlankText = Field(max_length=300)
    kind: NonBlankText = Field(max_length=80)
    scope: NonBlankText = Field(max_length=500)
    line: int = Field(ge=1, le=1_000_000)
    column: int = Field(default=0, ge=0, le=1_000_000)
    defined: bool = True
    use_count: int = Field(default=0, ge=0, le=1_000_000)
    inferred_type: str | None = Field(default=None, max_length=300)


class FunctionDTO(ContractModel):
    name: NonBlankText = Field(max_length=300)
    qualified_name: NonBlankText = Field(max_length=500)
    signature: NonBlankText = Field(max_length=2_000)
    line: int = Field(ge=1, le=1_000_000)
    end_line: int = Field(ge=1, le=1_000_000)
    parameters: tuple[str, ...] = Field(default=(), max_length=200)
    return_annotation: str | None = Field(default=None, max_length=500)
    decorators: tuple[str, ...] = Field(default=(), max_length=50)
    is_async: bool = False
    calls: tuple[str, ...] = Field(default=(), max_length=500)
    raises: tuple[str, ...] = Field(default=(), max_length=100)


class ClassDTO(ContractModel):
    name: NonBlankText = Field(max_length=300)
    qualified_name: NonBlankText = Field(max_length=500)
    line: int = Field(ge=1, le=1_000_000)
    end_line: int = Field(ge=1, le=1_000_000)
    bases: tuple[str, ...] = Field(default=(), max_length=50)
    decorators: tuple[str, ...] = Field(default=(), max_length=50)
    methods: tuple[str, ...] = Field(default=(), max_length=300)
    attributes: tuple[str, ...] = Field(default=(), max_length=500)


class TypeFactDTO(ContractModel):
    symbol: NonBlankText = Field(max_length=500)
    inferred_type: NonBlankText = Field(max_length=500)
    line: int = Field(ge=1, le=1_000_000)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence: NonBlankText = Field(max_length=2_000)


class CFGBlockDTO(ContractModel):
    id: NonBlankText = Field(max_length=500)
    scope: NonBlankText = Field(max_length=500)
    line: int = Field(ge=1, le=1_000_000)
    kind: NonBlankText = Field(max_length=80)
    label: NonBlankText = Field(max_length=1_000)
    successors: tuple[str, ...] = Field(default=(), max_length=20)


class CallEdgeDTO(ContractModel):
    caller: NonBlankText = Field(max_length=500)
    callee: NonBlankText = Field(max_length=500)
    line: int = Field(ge=1, le=1_000_000)
    dynamic: bool = False


class ComplexityFindingDTO(ContractModel):
    scope: NonBlankText = Field(max_length=500)
    cyclomatic: int = Field(ge=1, le=100_000)
    time: NonBlankText = Field(max_length=80)
    space: NonBlankText = Field(max_length=80)
    rationale: NonBlankText = Field(max_length=2_000)


class SecurityFindingDTO(ContractModel):
    code: NonBlankText = Field(max_length=120)
    severity: SnippetDiagnosticSeverity
    line: int = Field(ge=1, le=1_000_000)
    message: NonBlankText = Field(max_length=2_000)
    evidence: NonBlankText = Field(max_length=2_000)


class TestSuggestionDTO(ContractModel):
    name: NonBlankText = Field(max_length=300)
    rationale: NonBlankText = Field(max_length=2_000)
    category: NonBlankText = Field(max_length=80)
    code: str = Field(default="", max_length=10_000)


class OcrRegionDTO(ContractModel):
    text: str = Field(max_length=20_000)
    confidence: float = Field(ge=0.0, le=1.0)
    box: tuple[tuple[int, int], ...] = Field(default=(), max_length=8)
    ambiguous: bool = False


class OcrDraftDTO(ContractModel):
    text: str = Field(max_length=100_000)
    original_text: str = Field(default="", max_length=100_000)
    confidence: float = Field(ge=0.0, le=1.0)
    regions: tuple[OcrRegionDTO, ...] = Field(default=(), max_length=2_000)
    warnings: tuple[str, ...] = Field(default=(), max_length=100)
    requires_confirmation: bool = True
    normalization_status: str = Field(
        default="normalized", pattern=r"^(normalized|repaired|quarantined)$"
    )


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
    action: SnippetAction = SnippetAction.EXPLAIN
    action_result: str = Field(default="", max_length=20_000)
    diagnostics: tuple[DiagnosticDTO, ...] = Field(default=(), max_length=1_000)
    symbols: tuple[SymbolDTO, ...] = Field(default=(), max_length=5_000)
    functions: tuple[FunctionDTO, ...] = Field(default=(), max_length=1_000)
    classes: tuple[ClassDTO, ...] = Field(default=(), max_length=500)
    type_facts: tuple[TypeFactDTO, ...] = Field(default=(), max_length=5_000)
    cfg_blocks: tuple[CFGBlockDTO, ...] = Field(default=(), max_length=10_000)
    call_edges: tuple[CallEdgeDTO, ...] = Field(default=(), max_length=5_000)
    complexity_findings: tuple[ComplexityFindingDTO, ...] = Field(
        default=(), max_length=1_000
    )
    security_findings: tuple[SecurityFindingDTO, ...] = Field(default=(), max_length=500)
    test_suggestions: tuple[TestSuggestionDTO, ...] = Field(default=(), max_length=500)
    imports: tuple[str, ...] = Field(default=(), max_length=500)
    possible_exceptions: tuple[str, ...] = Field(default=(), max_length=500)
    node_count: int = Field(default=0, ge=0, le=100_000)
    elapsed_ms: float = Field(default=0.0, ge=0.0, le=60_000.0)
    analysis_truncated: bool = False
