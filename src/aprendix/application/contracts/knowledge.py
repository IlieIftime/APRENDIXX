"""Contracts for local knowledge, hybrid search, dashboards, and grading."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from pathlib import Path
from uuid import UUID, uuid4

from pydantic import Field, field_validator, model_validator

from aprendix.application.contracts.models import (
    ContractModel,
    NonBlankText,
    utc_now,
)
from aprendix.application.contracts.pedagogy import (
    CardFormat,
    CardSourceLinkDTO,
    PedagogicalBlockDTO,
)


class ContentKind(str, Enum):
    THEORY = "theory"
    EXERCISE = "exercise"
    PAPER = "paper"


class Complexity(str, Enum):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"


class EvidenceOrigin(str, Enum):
    LOCAL = "local"
    WEB = "web"


class SearchIntent(str, Enum):
    """Small, deterministic query-intent taxonomy used by the local ranker."""

    DEFINITION = "definition"
    HOW_TO = "how-to"
    EXAMPLE = "example"
    EXERCISE = "exercise"
    DEBUG = "debug"
    COMPARE = "compare"
    FORMULA = "formula"
    REFERENCE = "reference"
    EXPLORE = "explore"


class Technology(str, Enum):
    """Extensible catalogue taxonomy; executable desktop exercises remain Python."""

    PYTHON = "python"
    SQL = "sql"
    JAVA = "java"
    NOSQL = "nosql"
    DJANGO = "django"
    FASTAPI = "fastapi"
    FLASK = "flask"
    NUMPY = "numpy"
    PANDAS = "pandas"
    SCIPY = "scipy"
    SCIKIT_LEARN = "scikit-learn"
    PYTORCH = "pytorch"
    TENSORFLOW = "tensorflow"
    JUPYTER = "jupyter"
    HTML = "html"
    CSS = "css"
    JAVASCRIPT = "javascript"
    REACT = "react"
    BOOTSTRAP = "bootstrap"
    GO = "go"
    OTHER = "other"


class LearningTheme(str, Enum):
    FUNDAMENTALS = "fundamentals"
    OOP = "oop"
    ALGORITHMS = "algorithms"
    DATA_STRUCTURES = "data-structures"
    WEB = "web"
    DATA = "data"
    AI = "ai"
    FINANCE = "finance"
    GAMES = "games"
    DEVOPS = "devops"
    DATABASES = "databases"
    OTHER = "other"


class LearningMode(str, Enum):
    RECOMMENDED = "recommended"
    FREE = "free"


class KnowledgeClusterDTO(ContractModel):
    id: str = Field(min_length=1, max_length=160)
    label: NonBlankText = Field(max_length=160)
    member_count: int = Field(ge=0)
    technology: Technology | None = None
    theme: LearningTheme | None = None


class SearchFiltersDTO(ContractModel):
    preferred_authors: tuple[str, ...] = Field(default=(), max_length=30)
    content_types: tuple[ContentKind, ...] = ()
    complexities: tuple[Complexity, ...] = ()
    published_from: date | None = None
    published_to: date | None = None
    technologies: tuple[Technology, ...] = Field(default=(), max_length=20)
    themes: tuple[LearningTheme, ...] = Field(default=(), max_length=20)
    cluster_ids: tuple[str, ...] = Field(default=(), max_length=30)
    area_ids: tuple[str, ...] = Field(default=(), max_length=30)
    sources: tuple[str, ...] = Field(default=(), max_length=30)
    content_versions: tuple[str, ...] = Field(default=(), max_length=30)

    @field_validator("preferred_authors")
    @classmethod
    def authors_are_meaningful(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        cleaned = tuple(author.strip() for author in value if author.strip())
        if any(len(author) > 160 for author in cleaned):
            raise ValueError("author filters cannot exceed 160 characters")
        return cleaned

    @model_validator(mode="after")
    def dates_are_ordered(self) -> SearchFiltersDTO:
        if (
            self.published_from is not None
            and self.published_to is not None
            and self.published_from > self.published_to
        ):
            raise ValueError("published_from cannot follow published_to")
        return self


class SearchRequestDTO(ContractModel):
    query: NonBlankText = Field(max_length=2_000)
    filters: SearchFiltersDTO = Field(default_factory=SearchFiltersDTO)
    max_results: int = Field(default=8, ge=1, le=30)
    local_confidence_threshold: float = Field(default=0.48, ge=0.0, le=1.0)
    allow_web_fallback: bool = True


class SearchEvidenceDTO(ContractModel):
    id: str = Field(min_length=1, max_length=500)
    origin: EvidenceOrigin
    title: NonBlankText = Field(max_length=500)
    excerpt: NonBlankText = Field(max_length=4_000)
    source: NonBlankText = Field(max_length=2_000)
    relevance: float = Field(ge=0.0, le=1.0)
    author: str | None = Field(default=None, max_length=160)
    content_type: ContentKind
    complexity: Complexity
    published_at: date | None = None
    page_number: int | None = Field(default=None, ge=1)
    technologies: tuple[Technology, ...] = Field(default=(), max_length=20)
    themes: tuple[LearningTheme, ...] = Field(default=(), max_length=20)
    cluster_id: str | None = Field(default=None, max_length=160)
    why_shown: tuple[str, ...] = Field(default=(), max_length=8)
    lexical_score: float = Field(default=0.0, ge=0.0, le=1.0)
    semantic_score: float = Field(default=0.0, ge=0.0, le=1.0)
    rerank_score: float = Field(default=0.0, ge=0.0, le=1.0)


class SearchResponseDTO(ContractModel):
    query: NonBlankText = Field(max_length=2_000)
    answer: NonBlankText = Field(max_length=20_000)
    confidence: float = Field(ge=0.0, le=1.0)
    local_confidence: float = Field(ge=0.0, le=1.0)
    used_web_fallback: bool = False
    evidence: tuple[SearchEvidenceDTO, ...] = Field(default=(), max_length=30)
    fallback_reason: str | None = Field(default=None, max_length=500)
    similar_topics: tuple[KnowledgeClusterDTO, ...] = Field(default=(), max_length=12)
    intent: SearchIntent = SearchIntent.EXPLORE
    expanded_query: str = Field(default="", max_length=4_000)
    elapsed_ms: float = Field(default=0.0, ge=0.0)
    cancelled: bool = False


class TheoryCardDTO(ContractModel):
    id: UUID = Field(default_factory=uuid4)
    title: NonBlankText = Field(max_length=240)
    body: NonBlankText = Field(max_length=20_000)
    content_type: ContentKind = ContentKind.THEORY
    complexity: Complexity = Complexity.BEGINNER
    code_example: str = Field(default="", max_length=20_000)
    image_path: str | None = Field(default=None, max_length=2_000)
    source_title: str | None = Field(default=None, max_length=500)
    source_page: int | None = Field(default=None, ge=1)
    graph_node_id: UUID | None = None
    technologies: tuple[Technology, ...] = Field(default=(), max_length=20)
    themes: tuple[LearningTheme, ...] = Field(default=(), max_length=20)
    cluster_id: str | None = Field(default=None, max_length=160)
    area_ids: tuple[str, ...] = Field(default=(), max_length=20)
    format: CardFormat = CardFormat.CONCEPT
    formula_latex: str = Field(default="", max_length=2_000)
    formula_spoken: str = Field(default="", max_length=2_000)
    formula_variables: dict[str, str] = Field(default_factory=dict)
    formula_worked_example: str = Field(default="", max_length=4_000)
    asset_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    asset_alt_text: str = Field(default="", max_length=1_000)
    asset_uri: str = Field(default="", max_length=200)
    sources: tuple[CardSourceLinkDTO, ...] = Field(default=(), max_length=30)

    @field_validator("image_path")
    @classmethod
    def image_must_be_local(cls, value: str | None) -> str | None:
        if value is None:
            return None
        path = Path(value).expanduser()
        if not path.is_absolute():
            raise ValueError("theory card images must use an absolute local path")
        return str(path)


class KnowledgeAreaDTO(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    parent_id: str | None = Field(default=None, max_length=120)
    slug: NonBlankText = Field(max_length=120)
    title: NonBlankText = Field(max_length=160)
    description: NonBlankText = Field(max_length=1_000)
    depth: int = Field(ge=0, le=4)
    position: int = Field(ge=0)
    icon: str = Field(default="", max_length=20)
    recommended_order: int = Field(ge=0)
    card_count: int = Field(default=0, ge=0)
    source_count: int = Field(default=0, ge=0)


class SearchShortcutDTO(ContractModel):
    id: str = Field(min_length=1, max_length=160)
    area_id: str = Field(min_length=1, max_length=120)
    label: NonBlankText = Field(max_length=160)
    query: NonBlankText = Field(max_length=500)
    position: int = Field(ge=0)


class CuratedSourceDTO(ContractModel):
    id: str = Field(min_length=1, max_length=160)
    title: NonBlankText = Field(max_length=500)
    authors: tuple[str, ...] = Field(default=(), max_length=30)
    publication_year: int | None = Field(default=None, ge=1900, le=2200)
    source_type: str = Field(pattern=r"^(book|paper|course|documentation|report)$")
    canonical_url: str = Field(max_length=2_000)
    doi: str | None = Field(default=None, max_length=300)
    overview: NonBlankText = Field(max_length=8_000)
    why_it_matters: NonBlankText = Field(max_length=4_000)
    access_note: NonBlankText = Field(max_length=1_000)
    license_note: NonBlankText = Field(max_length=1_000)
    area_ids: tuple[str, ...] = Field(default=(), max_length=20)
    guidance_category: str = Field(
        default="aprofundamento",
        pattern=r"^(essencial agora|consulta rápida|aprofundamento|referência avançada|histórico/desatualizado)$",
    )
    recommended_sections: tuple[str, ...] = Field(default=(), max_length=12)
    difficulty: Complexity = Complexity.INTERMEDIATE
    estimated_minutes: int = Field(default=30, ge=1, le=10_000)
    version_scope: str = Field(default="conceitos estáveis", max_length=160)


class ReadingConceptDTO(ContractModel):
    term: NonBlankText = Field(max_length=160)
    definition: NonBlankText = Field(max_length=2_000)
    signature: str = Field(default="", max_length=1_000)
    related_terms: tuple[str, ...] = Field(default=(), max_length=20)


class ReadingDetailDTO(ContractModel):
    evidence_id: str = Field(min_length=1, max_length=500)
    title: NonBlankText = Field(max_length=500)
    source: NonBlankText = Field(max_length=2_000)
    original_content: NonBlankText = Field(max_length=100_000)
    summary: NonBlankText = Field(max_length=20_000)
    simplified: NonBlankText = Field(max_length=30_000)
    key_points: tuple[str, ...] = Field(default=(), max_length=20)
    math_notes: tuple[str, ...] = Field(default=(), max_length=20)
    concepts: tuple[ReadingConceptDTO, ...] = Field(default=(), max_length=40)
    visual_assets: tuple[str, ...] = Field(default=(), max_length=20)
    related_sources: tuple[CuratedSourceDTO, ...] = Field(default=(), max_length=20)
    canonical_url: str | None = Field(default=None, max_length=2_000)
    copyright_note: NonBlankText = Field(max_length=1_000)
    original_blocks: tuple[PedagogicalBlockDTO, ...] = Field(default=(), max_length=500)
    summary_blocks: tuple[PedagogicalBlockDTO, ...] = Field(default=(), max_length=200)
    simplified_blocks: tuple[PedagogicalBlockDTO, ...] = Field(default=(), max_length=300)


class DashboardNodeDTO(ContractModel):
    node_id: UUID
    title: NonBlankText = Field(max_length=160)
    mastery: float = Field(ge=0.0, le=1.0)
    attempts: int = Field(ge=0)
    recommended: bool = False


class DashboardDTO(ContractModel):
    generated_at: datetime = Field(default_factory=utc_now)
    overall_mastery: float = Field(default=0.0, ge=0.0, le=1.0)
    total_attempts: int = Field(default=0, ge=0)
    mastered_nodes: int = Field(default=0, ge=0)
    nodes: tuple[DashboardNodeDTO, ...] = ()


class IngestionSummaryDTO(ContractModel):
    run_id: UUID = Field(default_factory=uuid4)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    discovered_files: int = Field(default=0, ge=0)
    indexed_documents: int = Field(default=0, ge=0)
    skipped_documents: int = Field(default=0, ge=0)
    failed_documents: int = Field(default=0, ge=0)
    chunks: int = Field(default=0, ge=0)
    theory_cards: int = Field(default=0, ge=0)
    exercises: int = Field(default=0, ge=0)
    errors: tuple[str, ...] = Field(default=(), max_length=100)


class GradingTestCaseDTO(ContractModel):
    name: NonBlankText = Field(max_length=160)
    code: NonBlankText = Field(max_length=20_000)
    visibility: str = Field(default="public", pattern=r"^(public|hidden)$")
    kind: str = Field(default="example", pattern=r"^(example|property)$")
    weight: float = Field(default=1.0, gt=0.0, le=10.0)


class SmartCorrectionRequestDTO(ContractModel):
    source_code: NonBlankText = Field(max_length=100_000)
    tests: tuple[GradingTestCaseDTO, ...] = Field(default=(), max_length=50)
    required_constructs: tuple[str, ...] = Field(default=(), max_length=30)
    timeout_ms: int = Field(default=3_000, ge=100, le=15_000)

    @field_validator("required_constructs")
    @classmethod
    def constructs_are_ast_names(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        allowed = {
            "ClassDef", "FunctionDef", "AsyncFunctionDef", "For", "While",
            "If", "Try", "With", "ListComp", "DictComp", "SetComp",
            "GeneratorExp", "Return", "Raise",
        }
        unknown = sorted(set(value) - allowed)
        if unknown:
            raise ValueError(f"unknown required AST constructs: {unknown}")
        return value


class GradingTestOutcomeDTO(ContractModel):
    name: NonBlankText = Field(max_length=160)
    passed: bool
    message: str = Field(default="", max_length=2_000)
    visibility: str = Field(default="public", pattern=r"^(public|hidden)$")
    kind: str = Field(default="example", pattern=r"^(example|property)$")


class GradingRubricDTO(ContractModel):
    criterion: NonBlankText = Field(max_length=80)
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(gt=0.0, le=1.0)
    explanation: NonBlankText = Field(max_length=500)


class SmartCorrectionResponseDTO(ContractModel):
    score: float = Field(ge=0.0, le=1.0)
    status: str = Field(pattern=r"^(passed|failed|syntax_error|rejected|error)$")
    syntax_valid: bool
    policy_safe: bool
    test_outcomes: tuple[GradingTestOutcomeDTO, ...] = ()
    rubric: tuple[GradingRubricDTO, ...] = ()
    missing_constructs: tuple[str, ...] = ()
    feedback: tuple[str, ...] = Field(default=(), max_length=100)
