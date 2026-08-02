"""Behavior tests for deterministic CopyKate imitation and synthesis."""

import ast

import pytest

from aprendix.application import CopyKateService
from aprendix.application.contracts import (
    CodeEditDTO,
    CopyKateRequest,
    CopyKateResponse,
    SandboxRequest,
)
from aprendix.application.copykate_engine import CopyKateSyntaxError, diff_asts
from aprendix.infrastructure.sandbox import PythonSandbox


SOURCE = """\
def total_positive(values):
    result = 0
    for value in values:
        if value > 0:
            result += value
    return result
"""


def test_ngram_profile_learns_changed_tokens_and_style() -> None:
    edit = CodeEditDTO(
        before="""\
def total_positive(values):
    return 0
""",
        after=SOURCE,
    )

    response = CopyKateService().generate(
        CopyKateRequest(source_code=SOURCE, edits=(edit,), ngram_order=3)
    )

    assert response.profile.fallback_used is False
    assert response.profile.indent_width == 4
    assert response.profile.identifier_style == "snake_case"
    assert response.profile.transitions
    assert any(
        transition.next_token == "value"
        for transition in response.profile.transitions
    )


def test_copykate_returns_three_distinct_parseable_explainable_solutions() -> None:
    response = CopyKateService().generate(CopyKateRequest(source_code=SOURCE))

    assert [item.strategy for item in response.alternatives] == [
        "canonical",
        "nested_helper",
        "extracted_helper",
    ]
    assert len({item.source_code for item in response.alternatives}) == 3
    assert response.profile.fallback_used is True
    for alternative in response.alternatives:
        ast.parse(alternative.source_code)
        assert alternative.justification
    assert response.alternatives[1].ast_changes
    assert response.alternatives[2].ast_changes
    assert CopyKateResponse.model_validate_json(response.to_json()) == response


def test_copykate_contract_preserves_source_whitespace() -> None:
    source = "\nprint('kept')\n"

    request = CopyKateRequest(source_code=source)

    assert request.source_code == source


def test_generated_alternatives_preserve_common_function_result() -> None:
    response = CopyKateService().generate(CopyKateRequest(source_code=SOURCE))
    sandbox = PythonSandbox()

    results = [
        sandbox.run(
            SandboxRequest(
                source_code=(
                    alternative.source_code
                    + "\nprint(total_positive([-2, 3, 5]))\n"
                )
            )
        )
        for alternative in response.alternatives
    ]

    assert [result.status for result in results] == ["ok", "ok", "ok"]
    assert [result.stdout for result in results] == ["8\n", "8\n", "8\n"]


def test_script_fallback_produces_three_executable_variants() -> None:
    response = CopyKateService().generate(
        CopyKateRequest(source_code="print(sum(range(4)))")
    )
    sandbox = PythonSandbox()

    results = [
        sandbox.run(SandboxRequest(source_code=item.source_code))
        for item in response.alternatives
    ]

    assert [result.status for result in results] == ["ok", "ok", "ok"]
    assert [result.stdout for result in results] == ["6\n", "6\n", "6\n"]


def test_invalid_python_fails_without_placeholder_alternatives() -> None:
    with pytest.raises(CopyKateSyntaxError, match="invalid Python"):
        CopyKateService().generate(
            CopyKateRequest(source_code="def broken(:\n    return 1")
        )


def test_ast_diff_reports_field_paths_and_values() -> None:
    changes = diff_asts(ast.parse("answer = 1"), ast.parse("answer = 2"))

    assert len(changes) == 1
    assert changes[0].kind == "replace"
    assert changes[0].path.endswith(".value")
    assert changes[0].before == "1"
    assert changes[0].after == "2"
