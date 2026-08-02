"""Security and resource-boundary tests for isolated Python execution."""

import os

import pytest

from aprendix.application.contracts import SandboxRequest
from aprendix.infrastructure.sandbox import PythonAstPolicy, PythonSandbox


def test_safe_program_runs_with_deterministic_input() -> None:
    result = PythonSandbox().run(
        SandboxRequest(
            source_code="name = input('Name: ')\nprint(name.upper())",
            stdin=("Ada",),
        )
    )

    assert result.status == "ok"
    assert result.stdout == "Name: ADA\n"
    assert result.policy_violations == ()


@pytest.mark.parametrize(
    ("source", "rule"),
    [
        ("import os\nprint(os.getcwd())", "syntax.blocked"),
        ("open('secret.txt').read()", "name.blocked"),
        ("print((1).__class__)", "attribute.blocked"),
        ("print(__builtins__)", "name.dunder"),
        ("eval('1 + 1')", "name.blocked"),
    ],
)
def test_dangerous_capabilities_are_rejected_before_execution(
    source: str,
    rule: str,
) -> None:
    result = PythonSandbox().run(SandboxRequest(source_code=source))

    assert result.status == "rejected"
    assert rule in {violation.rule for violation in result.policy_violations}
    assert result.stdout == ""


def test_syntax_errors_are_policy_rejections() -> None:
    result = PythonSandbox().run(SandboxRequest(source_code="if True print(1)"))

    assert result.status == "rejected"
    assert result.policy_violations[0].rule == "syntax.invalid"


def test_runtime_errors_return_bounded_diagnostics() -> None:
    result = PythonSandbox().run(
        SandboxRequest(source_code="print(1 / 0)")
    )

    assert result.status == "runtime_error"
    assert result.error_type == "ZeroDivisionError"
    assert len(result.error_message or "") < 2_000


def test_infinite_loop_is_terminated_by_wall_clock_timeout() -> None:
    result = PythonSandbox().run(
        SandboxRequest(source_code="while True:\n    x = 1", timeout_ms=100)
    )

    assert result.status == "timeout"
    assert result.duration_ms < 3_000


def test_output_is_truncated_at_byte_limit() -> None:
    result = PythonSandbox().run(
        SandboxRequest(
            source_code="print('x' * 1000)",
            max_output_bytes=128,
        )
    )

    assert result.status == "output_limit"
    assert result.output_truncated is True
    assert len(result.stdout.encode("utf-8")) <= 128


def test_ast_node_budget_fails_closed() -> None:
    policy = PythonAstPolicy(max_ast_nodes=10)
    result = PythonSandbox(policy).run(
        SandboxRequest(source_code="values = [x * x for x in range(20)]")
    )

    assert result.status == "rejected"
    assert result.policy_violations[0].rule == "complexity.ast_nodes"


def test_memory_limit_capability_is_reported_truthfully() -> None:
    result = PythonSandbox().run(SandboxRequest(source_code="print(1)"))

    assert result.status == "ok"
    assert result.memory_limit_enforced is (os.name == "posix")

