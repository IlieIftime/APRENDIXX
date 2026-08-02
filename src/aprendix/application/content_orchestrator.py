"""Deterministic exercise templating with safe rule-based hint fallback."""

from __future__ import annotations

import random
import re
import string
import time
from collections.abc import Callable, Mapping, Sequence
from itertools import combinations
from typing import Protocol, TypeVar

from pydantic import ValidationError

from aprendix.application.content_ports import (
    NLPUnavailableError,
    QuantizedNLPAdapter,
)
from aprendix.application.contracts.content import (
    ConstraintKind,
    ExerciseConstraintDTO,
    ExerciseTemplateDTO,
    FadedHintDTO,
    FallbackReason,
    GeneratedExerciseDTO,
    GenerateExerciseRequest,
    HintSource,
    HintTemplateDTO,
    NLPHintRequestDTO,
    NLPHintResponseDTO,
    TemplateValue,
)

ChoiceT = TypeVar("ChoiceT")
_SAFE_FIELD = re.compile(r"^[a-z][a-z0-9_]*$")


class RandomSource(Protocol):
    """Small injectable surface implemented by ``random.Random``."""

    def choice(self, values: Sequence[ChoiceT]) -> ChoiceT:
        """Choose one member from a non-empty sequence."""


class OrchestrationError(RuntimeError):
    """Base error for invalid orchestration requests or templates."""


class UnknownTemplateError(OrchestrationError):
    """Raised when a request names a template absent from the local catalog."""


class TemplateRenderError(OrchestrationError):
    """Raised when a template contains unsafe or unresolved placeholders."""


class ConstraintSelectionError(OrchestrationError):
    """Raised when the requested set of compatible constraints cannot be formed."""


class _SafeFormatter(string.Formatter):
    """Allow exact scalar placeholders but no attribute/index traversal."""

    def get_field(
        self,
        field_name: str,
        args: Sequence[object],
        kwargs: Mapping[str, object],
    ) -> tuple[object, str]:
        if not _SAFE_FIELD.fullmatch(field_name):
            raise TemplateRenderError(f"unsafe template field: {field_name!r}")
        if field_name not in kwargs:
            raise TemplateRenderError(f"missing template parameter: {field_name}")
        return kwargs[field_name], field_name

    def convert_field(self, value: object, conversion: str | None) -> object:
        if conversion:
            raise TemplateRenderError("template conversions are not allowed")
        return value

    def format_field(self, value: object, format_spec: str) -> str:
        if format_spec:
            raise TemplateRenderError("template format specifications are not allowed")
        return str(value)


class ContentOrchestrator:
    """Instantiate templates, select valid constraints, and produce faded hints."""

    def __init__(
        self,
        templates: Sequence[ExerciseTemplateDTO],
        *,
        rng: RandomSource | None = None,
        nlp_adapter: QuantizedNLPAdapter | None = None,
        nlp_timeout_seconds: float = 0.25,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if nlp_timeout_seconds <= 0:
            raise ValueError("nlp_timeout_seconds must be positive")
        template_map = {template.id: template for template in templates}
        if len(template_map) != len(templates):
            raise ValueError("template ids must be unique")
        self._templates = template_map
        self._rng = rng or random.Random()
        self._nlp_adapter = nlp_adapter
        self._nlp_timeout_seconds = nlp_timeout_seconds
        self._clock = clock
        self._formatter = _SafeFormatter()

    def generate(self, request: GenerateExerciseRequest) -> GeneratedExerciseDTO:
        template = self._templates.get(request.template_id)
        if template is None:
            raise UnknownTemplateError(f"unknown exercise template: {request.template_id}")

        parameters = {
            parameter.name: self._rng.choice(parameter.choices)
            for parameter in template.parameters
        }
        requested_count = (
            template.default_constraint_count
            if request.constraint_count is None
            else request.constraint_count
        )
        constraints = self._select_constraints(template.constraints, requested_count)
        rendered_constraints = tuple(
            ExerciseConstraintDTO.model_validate(
                {
                    **constraint.model_dump(),
                    "instruction": self._render_required(
                        constraint.instruction,
                        parameters,
                        field_name="constraint instruction",
                    ),
                }
            )
            for constraint in constraints
        )

        title = self._render_required(template.title, parameters, field_name="title")
        base_prompt = self._render_required(
            template.prompt,
            parameters,
            field_name="prompt",
        )
        prompt = self._append_constraints(base_prompt, rendered_constraints)
        starter_code = self._render(template.starter_code, parameters)
        tests = tuple(
            self._render_required(test, parameters, field_name="test")
            for test in template.tests
        )
        baseline_hints = tuple(
            hint.model_copy(
                update={
                    "text": self._render_required(
                        hint.text,
                        parameters,
                        field_name="hint",
                    )
                }
            )
            for hint in template.hints
        )
        faded_hints = self._fade_for_proficiency(
            baseline_hints,
            request.proficiency,
        )
        hint_texts, hint_source, fallback_reason = self._generate_hint_texts(
            prompt,
            rendered_constraints,
            faded_hints,
        )
        hints = tuple(
            FadedHintDTO(
                stage=baseline.stage,
                guidance=baseline.guidance,
                text=text,
            )
            for baseline, text in zip(faded_hints, hint_texts)
        )

        return GeneratedExerciseDTO(
            template_id=template.id,
            graph_node_id=template.graph_node_id,
            title=title,
            prompt=prompt,
            starter_code=starter_code,
            tests=tests,
            parameters=parameters,
            constraints=rendered_constraints,
            hints=hints,
            hint_source=hint_source,
            fallback_reason=fallback_reason,
        )

    def _render(
        self,
        template: str,
        parameters: Mapping[str, TemplateValue],
    ) -> str:
        try:
            return self._formatter.vformat(template, (), parameters)
        except TemplateRenderError:
            raise
        except (KeyError, ValueError) as exc:
            raise TemplateRenderError(f"invalid exercise template: {exc}") from exc

    def _render_required(
        self,
        template: str,
        parameters: Mapping[str, TemplateValue],
        *,
        field_name: str,
    ) -> str:
        rendered = self._render(template, parameters)
        if not rendered.strip():
            raise TemplateRenderError(f"rendered {field_name} cannot be blank")
        return rendered

    @staticmethod
    def _constraints_are_compatible(
        constraints: Sequence[ExerciseConstraintDTO],
    ) -> bool:
        operations_by_target: dict[str, set[ConstraintKind]] = {}
        for constraint in constraints:
            operations_by_target.setdefault(constraint.target, set()).add(
                constraint.kind
            )
        return all(
            not {
                ConstraintKind.FORBID,
                ConstraintKind.REQUIRE,
            }.issubset(operations)
            for operations in operations_by_target.values()
        )

    def _select_constraints(
        self,
        pool: Sequence[ExerciseConstraintDTO],
        count: int,
    ) -> tuple[ExerciseConstraintDTO, ...]:
        if count == 0:
            return ()
        if count > len(pool):
            raise ConstraintSelectionError(
                f"requested {count} constraints from a pool of {len(pool)}"
            )
        valid_combinations = tuple(
            candidate
            for candidate in combinations(pool, count)
            if self._constraints_are_compatible(candidate)
        )
        if not valid_combinations:
            raise ConstraintSelectionError(
                f"no compatible combination of {count} constraints exists"
            )
        return tuple(self._rng.choice(valid_combinations))

    @staticmethod
    def _append_constraints(
        prompt: str,
        constraints: Sequence[ExerciseConstraintDTO],
    ) -> str:
        if not constraints:
            return prompt
        instructions = "\n".join(
            f"- {constraint.instruction}" for constraint in constraints
        )
        return f"{prompt}\n\nConstraints:\n{instructions}"

    @staticmethod
    def _fade_for_proficiency(
        hints: Sequence[HintTemplateDTO],
        proficiency: float,
    ) -> tuple[HintTemplateDTO, ...]:
        start = min(int(proficiency * len(hints)), len(hints) - 1)
        return tuple(hints[start:])

    def _generate_hint_texts(
        self,
        prompt: str,
        constraints: Sequence[ExerciseConstraintDTO],
        baseline_hints: Sequence[HintTemplateDTO],
    ) -> tuple[tuple[str, ...], HintSource, FallbackReason | None]:
        fallback = tuple(hint.text for hint in baseline_hints)
        if self._nlp_adapter is None:
            return fallback, HintSource.RULE_BASED, FallbackReason.NOT_CONFIGURED

        request = NLPHintRequestDTO(
            prompt=prompt,
            constraints=tuple(
                constraint.instruction for constraint in constraints
            ),
            baseline_hints=fallback,
        )
        started_at = self._clock()
        try:
            raw_response = self._nlp_adapter.generate_hints(
                request,
                timeout_seconds=self._nlp_timeout_seconds,
            )
            elapsed = self._clock() - started_at
            if elapsed > self._nlp_timeout_seconds:
                return fallback, HintSource.RULE_BASED, FallbackReason.TIMEOUT
            response = NLPHintResponseDTO.model_validate(raw_response)
            if len(response.hints) != len(baseline_hints):
                return (
                    fallback,
                    HintSource.RULE_BASED,
                    FallbackReason.INVALID_RESPONSE,
                )
            return tuple(response.hints), HintSource.QUANTIZED_NLP, None
        except TimeoutError:
            return fallback, HintSource.RULE_BASED, FallbackReason.TIMEOUT
        except NLPUnavailableError:
            return fallback, HintSource.RULE_BASED, FallbackReason.UNAVAILABLE
        except (ValidationError, TypeError, ValueError):
            return fallback, HintSource.RULE_BASED, FallbackReason.INVALID_RESPONSE
        except Exception:
            return fallback, HintSource.RULE_BASED, FallbackReason.ERROR
