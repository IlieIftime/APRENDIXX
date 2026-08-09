"""Minimal JSON contracts for dynamic exercise orchestration."""

from __future__ import annotations

from aprendix.domain.enums import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator, model_validator

from aprendix.application.contracts.models import ContractModel, NonBlankText, Slug

ParameterName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_]*$",
    ),
]
TemplateValue = str | int | float | bool


class ConstraintKind(StrEnum):
    """Constraint operations understood by the template engine."""

    FORBID = "forbid"
    REQUIRE = "require"
    LIMIT = "limit"


class HintStage(StrEnum):
    """Ordered stages whose scaffolding deliberately fades."""

    WORKED_EXAMPLE = "worked_example"
    SCAFFOLD = "scaffold"
    CUE = "cue"


class HintSource(StrEnum):
    """Source used for the final hint text."""

    QUANTIZED_NLP = "quantized_nlp"
    RULE_BASED = "rule_based"


class FallbackReason(StrEnum):
    """Non-sensitive reason why deterministic hints were selected."""

    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    INVALID_RESPONSE = "invalid_response"
    ERROR = "error"


class TemplateParameterDTO(ContractModel):
    """A named placeholder and its finite set of safe JSON scalar choices."""

    name: ParameterName
    choices: tuple[TemplateValue, ...] = Field(min_length=1, max_length=50)

    @field_validator("choices")
    @classmethod
    def choices_must_be_distinct(
        cls,
        choices: tuple[TemplateValue, ...],
    ) -> tuple[TemplateValue, ...]:
        identities = {(type(value).__name__, repr(value)) for value in choices}
        if len(identities) != len(choices):
            raise ValueError("parameter choices must be distinct")
        return choices


class ExerciseConstraintDTO(ContractModel):
    """A renderable and machine-readable exercise constraint."""

    id: Slug
    kind: ConstraintKind
    target: ParameterName
    instruction: NonBlankText = Field(max_length=500)
    value: int | None = Field(default=None, ge=1, le=10_000)

    @model_validator(mode="after")
    def validate_value_shape(self) -> ExerciseConstraintDTO:
        if self.kind is ConstraintKind.LIMIT and self.value is None:
            raise ValueError("limit constraints require a positive value")
        if self.kind is not ConstraintKind.LIMIT and self.value is not None:
            raise ValueError("only limit constraints accept a value")
        return self


class HintTemplateDTO(ContractModel):
    """A rule-based hint template at a known scaffolding strength."""

    stage: HintStage
    guidance: float = Field(gt=0.0, le=1.0)
    text: NonBlankText = Field(max_length=2_000)


class ExerciseTemplateDTO(ContractModel):
    """Validated source material from which concrete exercises are rendered."""

    id: Slug
    graph_node_id: UUID
    title: NonBlankText = Field(max_length=160)
    prompt: NonBlankText = Field(max_length=20_000)
    starter_code: str = Field(default="", max_length=50_000)
    tests: tuple[NonBlankText, ...] = Field(min_length=1, max_length=100)
    parameters: tuple[TemplateParameterDTO, ...] = Field(
        default_factory=tuple,
        max_length=25,
    )
    constraints: tuple[ExerciseConstraintDTO, ...] = Field(
        default_factory=tuple,
        max_length=25,
    )
    default_constraint_count: int = Field(default=0, ge=0, le=5)
    hints: tuple[HintTemplateDTO, ...] = Field(min_length=1, max_length=5)

    @model_validator(mode="after")
    def validate_template_structure(self) -> ExerciseTemplateDTO:
        parameter_names = [parameter.name for parameter in self.parameters]
        if len(set(parameter_names)) != len(parameter_names):
            raise ValueError("template parameter names must be unique")

        constraint_ids = [constraint.id for constraint in self.constraints]
        if len(set(constraint_ids)) != len(constraint_ids):
            raise ValueError("template constraint ids must be unique")
        if self.default_constraint_count > len(self.constraints):
            raise ValueError("default_constraint_count exceeds the constraint pool")

        expected_stages = (
            HintStage.WORKED_EXAMPLE,
            HintStage.SCAFFOLD,
            HintStage.CUE,
        )
        stage_positions = [expected_stages.index(hint.stage) for hint in self.hints]
        if stage_positions != sorted(stage_positions):
            raise ValueError("hint stages must follow the faded-guidance order")
        if len(set(stage_positions)) != len(stage_positions):
            raise ValueError("hint stages must be unique")
        guidance = [hint.guidance for hint in self.hints]
        if any(left <= right for left, right in zip(guidance, guidance[1:])):
            raise ValueError("hint guidance must strictly decrease")
        return self


class GenerateExerciseRequest(ContractModel):
    """Small command accepted by the content orchestrator."""

    template_id: Slug
    proficiency: float = Field(default=0.0, ge=0.0, le=1.0)
    constraint_count: int | None = Field(default=None, ge=0, le=5)


class NLPHintRequestDTO(ContractModel):
    """Bounded input sent to an optional on-device quantized adapter."""

    prompt: NonBlankText = Field(max_length=20_000)
    constraints: tuple[str, ...] = Field(default_factory=tuple, max_length=5)
    baseline_hints: tuple[NonBlankText, ...] = Field(min_length=1, max_length=5)


class NLPHintResponseDTO(ContractModel):
    """Strict adapter output; malformed model output never reaches callers."""

    hints: tuple[NonBlankText, ...] = Field(min_length=1, max_length=5)


class FadedHintDTO(ContractModel):
    """A concrete hint whose numerical guidance decreases across the sequence."""

    stage: HintStage
    guidance: float = Field(gt=0.0, le=1.0)
    text: NonBlankText = Field(max_length=2_000)


class GeneratedExerciseDTO(ContractModel):
    """Fully rendered exercise returned through the local JSON boundary."""

    template_id: Slug
    graph_node_id: UUID
    title: NonBlankText = Field(max_length=160)
    prompt: NonBlankText = Field(max_length=20_000)
    starter_code: str = Field(default="", max_length=50_000)
    tests: tuple[NonBlankText, ...] = Field(min_length=1, max_length=100)
    parameters: dict[ParameterName, TemplateValue] = Field(default_factory=dict)
    constraints: tuple[ExerciseConstraintDTO, ...] = Field(
        default_factory=tuple,
        max_length=5,
    )
    hints: tuple[FadedHintDTO, ...] = Field(min_length=1, max_length=5)
    hint_source: HintSource
    fallback_reason: FallbackReason | None = None

    @model_validator(mode="after")
    def validate_hint_metadata(self) -> GeneratedExerciseDTO:
        if self.hint_source is HintSource.QUANTIZED_NLP:
            if self.fallback_reason is not None:
                raise ValueError("NLP hints cannot include a fallback reason")
        elif self.fallback_reason is None:
            raise ValueError("rule-based hints require a fallback reason")

        guidance = [hint.guidance for hint in self.hints]
        if any(left <= right for left, right in zip(guidance, guidance[1:])):
            raise ValueError("generated hint guidance must strictly decrease")
        return self
