"""Versioned contracts for CopyKate imitation, synthesis, and sandboxing."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import (
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from aprendix.application.contracts.models import ContractModel

SourceCode = Annotated[
    str,
    StringConstraints(min_length=1, max_length=100_000),
]


class CodeEditDTO(ContractModel):
    """One user edit used to learn local token-transition preferences."""

    model_config = ConfigDict(str_strip_whitespace=False)

    before: str = Field(max_length=100_000)
    after: str = Field(max_length=100_000)

    @model_validator(mode="after")
    def edit_must_change_source(self) -> CodeEditDTO:
        if self.before == self.after:
            raise ValueError("an edit must change the source")
        return self


class NGramTransitionDTO(ContractModel):
    """A learned next-token probability for a token context."""

    context: tuple[str, ...] = Field(max_length=4)
    next_token: str = Field(min_length=1, max_length=200)
    count: int = Field(ge=1)
    probability: float = Field(ge=0.0, le=1.0)


class ImitationProfileDTO(ContractModel):
    """Compact, serializable representation of the user's editing style."""

    ngram_order: int = Field(ge=2, le=5)
    transitions: tuple[NGramTransitionDTO, ...] = Field(max_length=500)
    indent_width: int = Field(ge=1, le=8)
    quote_style: Literal["single", "double"]
    identifier_style: Literal["snake_case", "camelCase", "mixed"]
    fallback_used: bool

    def suggest(self, context: tuple[str, ...], *, limit: int = 3) -> tuple[str, ...]:
        """Return deterministic, probability-ranked next tokens."""

        if limit < 1:
            raise ValueError("limit must be positive")
        suffix = context[-(self.ngram_order - 1) :]
        candidates = [
            transition
            for transition in self.transitions
            if transition.context == suffix
        ]
        candidates.sort(
            key=lambda item: (-item.probability, -item.count, item.next_token)
        )
        return tuple(item.next_token for item in candidates[:limit])


class AstChangeDTO(ContractModel):
    """One structural difference between two Python abstract syntax trees."""

    kind: Literal["add", "remove", "replace"]
    path: str = Field(min_length=1, max_length=500)
    before: str | None = Field(default=None, max_length=2_000)
    after: str | None = Field(default=None, max_length=2_000)


class AlternativeSolutionDTO(ContractModel):
    """A complete generated solution with explainable structural changes."""

    model_config = ConfigDict(str_strip_whitespace=False)

    strategy: Literal["canonical", "nested_helper", "extracted_helper"]
    source_code: SourceCode
    justification: str = Field(min_length=1, max_length=2_000)
    ast_changes: tuple[AstChangeDTO, ...] = Field(max_length=250)


class CopyKateRequest(ContractModel):
    """Input to the deterministic, local CopyKate engine."""

    model_config = ConfigDict(str_strip_whitespace=False)

    source_code: SourceCode
    edits: tuple[CodeEditDTO, ...] = Field(default_factory=tuple, max_length=100)
    ngram_order: int = Field(default=3, ge=2, le=5)

    @field_validator("source_code")
    @classmethod
    def source_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_code cannot be blank")
        return value


class CopyKateResponse(ContractModel):
    """Exactly three distinct alternatives and the learned imitation profile."""

    profile: ImitationProfileDTO
    alternatives: tuple[
        AlternativeSolutionDTO,
        AlternativeSolutionDTO,
        AlternativeSolutionDTO,
    ]

    @field_validator("alternatives")
    @classmethod
    def alternatives_must_be_distinct(
        cls,
        value: tuple[
            AlternativeSolutionDTO,
            AlternativeSolutionDTO,
            AlternativeSolutionDTO,
        ],
    ) -> tuple[
        AlternativeSolutionDTO,
        AlternativeSolutionDTO,
        AlternativeSolutionDTO,
    ]:
        if len({alternative.source_code for alternative in value}) != 3:
            raise ValueError("CopyKate alternatives must be distinct")
        return value


class PolicyViolationDTO(ContractModel):
    """A source-policy rejection with a stable machine-readable rule."""

    rule: str = Field(min_length=1, max_length=80)
    message: str = Field(min_length=1, max_length=500)
    line: int = Field(ge=1)
    column: int = Field(ge=0)


class SandboxRequest(ContractModel):
    """Limits and deterministic input for one isolated Python execution."""

    model_config = ConfigDict(str_strip_whitespace=False)

    source_code: SourceCode
    stdin: tuple[str, ...] = Field(default_factory=tuple, max_length=100)
    timeout_ms: int = Field(default=1_000, ge=50, le=10_000)
    max_output_bytes: int = Field(default=16_384, ge=128, le=262_144)
    memory_limit_mb: int = Field(default=256, ge=64, le=1_024)

    @field_validator("source_code")
    @classmethod
    def sandbox_source_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("source_code cannot be blank")
        return value

    @field_validator("stdin")
    @classmethod
    def limit_individual_input(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(len(item.encode("utf-8")) > 65_536 for item in value):
            raise ValueError("each stdin item must be at most 65536 UTF-8 bytes")
        return value


class SandboxResult(ContractModel):
    """Fail-closed sandbox outcome; non-OK statuses never imply safe execution."""

    model_config = ConfigDict(str_strip_whitespace=False)

    status: Literal[
        "ok",
        "rejected",
        "runtime_error",
        "timeout",
        "output_limit",
        "resource_limit",
        "infrastructure_error",
    ]
    stdout: str = Field(default="", max_length=262_144)
    duration_ms: int = Field(ge=0)
    exit_code: int | None = None
    error_type: str | None = Field(default=None, max_length=200)
    error_message: str | None = Field(default=None, max_length=2_000)
    policy_violations: tuple[PolicyViolationDTO, ...] = Field(
        default_factory=tuple,
        max_length=100,
    )
    memory_limit_enforced: bool
    output_truncated: bool = False
