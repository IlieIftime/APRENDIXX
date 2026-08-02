"""Sprint 4 content-orchestrator behavior and fallback tests."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError

from aprendix.application import (
    ConstraintSelectionError,
    ContentOrchestrator,
    NLPUnavailableError,
    TemplateRenderError,
    UnknownTemplateError,
)
from aprendix.application.contracts import (
    ConstraintKind,
    ExerciseConstraintDTO,
    ExerciseTemplateDTO,
    FallbackReason,
    GeneratedExerciseDTO,
    GenerateExerciseRequest,
    HintSource,
    HintStage,
    HintTemplateDTO,
    NLPHintResponseDTO,
    TemplateParameterDTO,
)


class FirstChoiceRng:
    """Predictable random source used to assert exact rendering."""

    def choice(self, values: Sequence[Any]) -> Any:
        return values[0]


def make_template(**changes: Any) -> ExerciseTemplateDTO:
    values: dict[str, Any] = {
        "id": "sum-range",
        "graph_node_id": uuid4(),
        "title": "Sum {item_count} values",
        "prompt": (
            "Implement {function_name} to add the first {item_count} positive "
            "integers."
        ),
        "starter_code": "def {function_name}():\n    return 0",
        "tests": (
            "assert {function_name}() == {expected_total}",
            "assert callable({function_name})",
        ),
        "parameters": (
            TemplateParameterDTO(name="item_count", choices=(3, 5)),
            TemplateParameterDTO(name="expected_total", choices=(6, 15)),
            TemplateParameterDTO(name="function_name", choices=("sum_first", "total")),
        ),
        "constraints": (
            ExerciseConstraintDTO(
                id="no-loops",
                kind=ConstraintKind.FORBID,
                target="loops",
                instruction="Do not use loops.",
            ),
            ExerciseConstraintDTO(
                id="use-loop",
                kind=ConstraintKind.REQUIRE,
                target="loops",
                instruction="Use one loop.",
            ),
            ExerciseConstraintDTO(
                id="max-eight-lines",
                kind=ConstraintKind.LIMIT,
                target="lines",
                value=8,
                instruction="Use at most 8 lines.",
            ),
        ),
        "default_constraint_count": 2,
        "hints": (
            HintTemplateDTO(
                stage=HintStage.WORKED_EXAMPLE,
                guidance=1.0,
                text="For {item_count}, first write the additions explicitly.",
            ),
            HintTemplateDTO(
                stage=HintStage.SCAFFOLD,
                guidance=0.6,
                text="Plan how {function_name} accumulates each value.",
            ),
            HintTemplateDTO(
                stage=HintStage.CUE,
                guidance=0.2,
                text="Check the boundary at {item_count}.",
            ),
        ),
    }
    values.update(changes)
    return ExerciseTemplateDTO(**values)


def request(**changes: Any) -> GenerateExerciseRequest:
    values: dict[str, Any] = {
        "template_id": "sum-range",
        "proficiency": 0.0,
    }
    values.update(changes)
    return GenerateExerciseRequest(**values)


def test_template_engine_renders_parameters_and_valid_constraints() -> None:
    template = make_template()
    orchestrator = ContentOrchestrator((template,), rng=FirstChoiceRng())

    result = orchestrator.generate(request())

    assert result.title == "Sum 3 values"
    assert "sum_first" in result.prompt
    assert result.starter_code.startswith("def sum_first")
    assert result.tests[0] == "assert sum_first() == 6"
    assert result.parameters == {
        "item_count": 3,
        "expected_total": 6,
        "function_name": "sum_first",
    }
    assert [constraint.id for constraint in result.constraints] == [
        "no-loops",
        "max-eight-lines",
    ]
    assert "Constraints:\n- Do not use loops.\n- Use at most 8 lines." in result.prompt


def test_injected_seeded_rng_is_reproducible() -> None:
    template = make_template()
    first = ContentOrchestrator((template,), rng=random.Random(91))
    second = ContentOrchestrator((template,), rng=random.Random(91))

    assert first.generate(request()) == second.generate(request())


@pytest.mark.parametrize("seed", range(20))
def test_random_constraint_selection_never_returns_conflicting_rules(seed: int) -> None:
    result = ContentOrchestrator(
        (make_template(),),
        rng=random.Random(seed),
    ).generate(request())

    operations = {
        constraint.kind
        for constraint in result.constraints
        if constraint.target == "loops"
    }
    assert not {
        ConstraintKind.FORBID,
        ConstraintKind.REQUIRE,
    }.issubset(operations)


def test_impossible_constraint_count_is_rejected() -> None:
    template = make_template(
        constraints=(
            ExerciseConstraintDTO(
                id="no-loops",
                kind=ConstraintKind.FORBID,
                target="loops",
                instruction="Do not use loops.",
            ),
            ExerciseConstraintDTO(
                id="use-loop",
                kind=ConstraintKind.REQUIRE,
                target="loops",
                instruction="Use one loop.",
            ),
        ),
        default_constraint_count=1,
    )
    orchestrator = ContentOrchestrator((template,), rng=FirstChoiceRng())

    with pytest.raises(ConstraintSelectionError, match="no compatible"):
        orchestrator.generate(request(constraint_count=2))


def test_missing_or_unsafe_placeholders_fail_closed() -> None:
    missing = make_template(prompt="Use {unknown_parameter}.")
    unsafe = make_template(prompt="Use {function_name.__class__}.")

    with pytest.raises(TemplateRenderError, match="missing"):
        ContentOrchestrator((missing,), rng=FirstChoiceRng()).generate(request())
    with pytest.raises(TemplateRenderError, match="unsafe"):
        ContentOrchestrator((unsafe,), rng=FirstChoiceRng()).generate(request())


def test_unknown_template_has_explicit_application_error() -> None:
    orchestrator = ContentOrchestrator((make_template(),))

    with pytest.raises(UnknownTemplateError, match="missing-template"):
        orchestrator.generate(
            GenerateExerciseRequest(template_id="missing-template")
        )


def test_faded_guidance_removes_heavy_scaffolding_for_proficient_user() -> None:
    novice = ContentOrchestrator(
        (make_template(),),
        rng=FirstChoiceRng(),
    ).generate(request(proficiency=0.0))
    proficient = ContentOrchestrator(
        (make_template(),),
        rng=FirstChoiceRng(),
    ).generate(request(proficiency=0.8))

    assert [hint.stage for hint in novice.hints] == [
        HintStage.WORKED_EXAMPLE,
        HintStage.SCAFFOLD,
        HintStage.CUE,
    ]
    assert [hint.guidance for hint in novice.hints] == [1.0, 0.6, 0.2]
    assert [hint.stage for hint in proficient.hints] == [HintStage.CUE]


class SuccessfulAdapter:
    def __init__(self) -> None:
        self.request = None
        self.timeout = None

    def generate_hints(self, request, *, timeout_seconds):
        self.request = request
        self.timeout = timeout_seconds
        return NLPHintResponseDTO(
            hints=tuple(
                f"local-model-{index}"
                for index, _ in enumerate(request.baseline_hints, start=1)
            )
        )


def test_quantized_adapter_receives_bounded_request_and_replaces_hint_text() -> None:
    adapter = SuccessfulAdapter()
    result = ContentOrchestrator(
        (make_template(),),
        rng=FirstChoiceRng(),
        nlp_adapter=adapter,
        nlp_timeout_seconds=0.1,
    ).generate(request(proficiency=0.8))

    assert result.hint_source is HintSource.QUANTIZED_NLP
    assert result.fallback_reason is None
    assert [hint.text for hint in result.hints] == ["local-model-1"]
    assert adapter.timeout == 0.1
    assert adapter.request.constraints == (
        "Do not use loops.",
        "Use at most 8 lines.",
    )


class RaisingAdapter:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def generate_hints(self, request, *, timeout_seconds):
        raise self.error


@pytest.mark.parametrize(
    ("error", "reason"),
    (
        (NLPUnavailableError("model absent"), FallbackReason.UNAVAILABLE),
        (TimeoutError("budget exceeded"), FallbackReason.TIMEOUT),
        (RuntimeError("runtime crashed"), FallbackReason.ERROR),
    ),
)
def test_adapter_failures_use_complete_rule_based_fallback(
    error: Exception,
    reason: FallbackReason,
) -> None:
    result = ContentOrchestrator(
        (make_template(),),
        rng=FirstChoiceRng(),
        nlp_adapter=RaisingAdapter(error),
    ).generate(request())

    assert result.hint_source is HintSource.RULE_BASED
    assert result.fallback_reason is reason
    assert [hint.text for hint in result.hints] == [
        "For 3, first write the additions explicitly.",
        "Plan how sum_first accumulates each value.",
        "Check the boundary at 3.",
    ]


class InvalidAdapter:
    def generate_hints(self, request, *, timeout_seconds):
        return {"hints": ["only one"]}


def test_wrong_hint_count_from_adapter_uses_rule_based_fallback() -> None:
    result = ContentOrchestrator(
        (make_template(),),
        rng=FirstChoiceRng(),
        nlp_adapter=InvalidAdapter(),
    ).generate(request())

    assert result.hint_source is HintSource.RULE_BASED
    assert result.fallback_reason is FallbackReason.INVALID_RESPONSE
    assert len(result.hints) == 3


class SlowAdapter(SuccessfulAdapter):
    """Semantic test double whose lateness is supplied by the injected clock."""


def test_adapter_response_after_latency_budget_is_discarded() -> None:
    times = iter((10.0, 10.6))
    result = ContentOrchestrator(
        (make_template(),),
        rng=FirstChoiceRng(),
        nlp_adapter=SlowAdapter(),
        nlp_timeout_seconds=0.25,
        clock=lambda: next(times),
    ).generate(request())

    assert result.hint_source is HintSource.RULE_BASED
    assert result.fallback_reason is FallbackReason.TIMEOUT
    assert result.hints[0].text.startswith("For 3")


def test_no_adapter_is_an_explicit_deterministic_fallback() -> None:
    result = ContentOrchestrator(
        (make_template(),),
        rng=FirstChoiceRng(),
    ).generate(request())

    assert result.hint_source is HintSource.RULE_BASED
    assert result.fallback_reason is FallbackReason.NOT_CONFIGURED


def test_generated_contract_round_trips_through_minimal_json_boundary() -> None:
    result = ContentOrchestrator(
        (make_template(),),
        rng=FirstChoiceRng(),
    ).generate(request(proficiency=0.8))

    restored = GeneratedExerciseDTO.model_validate_json(result.to_json())

    assert restored == result
    assert '"hint_source":"rule_based"' in result.to_json()


def test_contracts_reject_invalid_limit_and_non_fading_hint_order() -> None:
    with pytest.raises(ValidationError, match="positive value"):
        ExerciseConstraintDTO(
            id="bad-limit",
            kind=ConstraintKind.LIMIT,
            target="lines",
            instruction="Keep it short.",
        )

    with pytest.raises(ValidationError, match="strictly decrease"):
        make_template(
            hints=(
                HintTemplateDTO(
                    stage=HintStage.WORKED_EXAMPLE,
                    guidance=0.5,
                    text="Detailed.",
                ),
                HintTemplateDTO(
                    stage=HintStage.CUE,
                    guidance=0.8,
                    text="Cue.",
                ),
            )
        )
