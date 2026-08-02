"""Deterministic AST and isolated-test based correction service."""

from __future__ import annotations

import ast
from typing import Protocol

from aprendix.application.contracts import (
    GradingTestOutcomeDTO,
    SmartCorrectionRequestDTO,
    SmartCorrectionResponseDTO,
)


class GradingPolicy(Protocol):
    def violations(self, source: str, *, trusted_test: bool = False) -> tuple[str, ...]: ...


class GradingExecutor(Protocol):
    def run_test(self, source: str, test_code: str, *, timeout_ms: int) -> tuple[str, str]: ...


class SmartCorrector:
    def __init__(self, policy: GradingPolicy, executor: GradingExecutor) -> None:
        self._policy = policy
        self._executor = executor

    def correct(self, request: SmartCorrectionRequestDTO) -> SmartCorrectionResponseDTO:
        try:
            tree = ast.parse(request.source_code, mode="exec")
        except SyntaxError as exc:
            location = f"linha {exc.lineno or 0}, coluna {exc.offset or 0}"
            return SmartCorrectionResponseDTO(
                score=0.0, status="syntax_error", syntax_valid=False,
                policy_safe=False,
                feedback=(f"Erro de sintaxe em {location}: {exc.msg}",),
            )
        violations = self._policy.violations(request.source_code)
        if violations:
            return SmartCorrectionResponseDTO(
                score=0.0, status="rejected", syntax_valid=True,
                policy_safe=False, feedback=violations,
            )
        present = {type(node).__name__ for node in ast.walk(tree)}
        missing = tuple(sorted(set(request.required_constructs) - present))
        outcomes: list[GradingTestOutcomeDTO] = []
        for test in request.tests:
            test_violations = self._policy.violations(test.code, trusted_test=True)
            if test_violations:
                outcomes.append(
                    GradingTestOutcomeDTO(
                        name=test.name, passed=False,
                        message="O teste armazenado foi rejeitado pela política de segurança.",
                    )
                )
                continue
            status, message = self._executor.run_test(
                request.source_code, test.code, timeout_ms=request.timeout_ms
            )
            outcomes.append(
                GradingTestOutcomeDTO(
                    name=test.name, passed=status == "passed",
                    message=message[:2_000],
                )
            )
        if request.tests:
            passed_ratio = sum(item.passed for item in outcomes) / len(request.tests)
        else:
            passed_ratio = 0.0
        construct_ratio = (
            1.0 - len(missing) / len(request.required_constructs)
            if request.required_constructs else 1.0
        )
        score = round(0.8 * passed_ratio + 0.2 * construct_ratio, 4)
        passed = score == 1.0 and not missing and all(item.passed for item in outcomes)
        feedback: list[str] = []
        if missing:
            feedback.append("Estruturas AST em falta: " + ", ".join(missing))
        failed = [item.name for item in outcomes if not item.passed]
        if failed:
            feedback.append("Testes a rever: " + ", ".join(failed))
        if not request.tests:
            feedback.append("Não existem testes aprovados para validar a correção dinâmica.")
        if passed:
            feedback.append("Solução validada pela análise AST e pelos testes isolados.")
        elif not feedback:
            feedback.append("A solução é sintaticamente válida, mas requer revisão.")
        return SmartCorrectionResponseDTO(
            score=score, status="passed" if passed else "failed",
            syntax_valid=True, policy_safe=True,
            test_outcomes=tuple(outcomes), missing_constructs=missing,
            feedback=tuple(feedback),
        )
