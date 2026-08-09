"""Deterministic AST and isolated-test based correction service."""

from __future__ import annotations

import ast
from typing import Protocol

from aprendix.application.contracts import (
    GradingRubricDTO, GradingTestOutcomeDTO,
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
                        visibility=test.visibility, kind=test.kind,
                    )
                )
                continue
            status, message = self._executor.run_test(
                request.source_code, test.code, timeout_ms=request.timeout_ms
            )
            outcomes.append(
                GradingTestOutcomeDTO(
                    name=test.name, passed=status == "passed",
                    message=(message[:2_000] if test.visibility == "public" else
                             ("Teste oculto concluído." if status == "passed" else
                              "Um caso oculto não foi satisfeito; revê os limites e invariantes.")),
                    visibility=test.visibility, kind=test.kind,
                )
            )
        if request.tests:
            total_weight = sum(test.weight for test in request.tests)
            passed_ratio = sum(
                test.weight for test, item in zip(request.tests, outcomes, strict=True)
                if item.passed
            ) / total_weight
        else:
            passed_ratio = 0.0
        construct_ratio = (
            1.0 - len(missing) / len(request.required_constructs)
            if request.required_constructs else 1.0
        )
        style_findings = self._style_findings(tree)
        style_ratio = max(0.0, 1.0 - 0.2 * len(style_findings))
        rubric = (
            GradingRubricDTO(
                criterion="Resultado", score=passed_ratio, weight=0.65,
                explanation="Casos públicos, ocultos e propriedades executados no processo isolado.",
            ),
            GradingRubricDTO(
                criterion="Estrutura", score=construct_ratio, weight=0.25,
                explanation="Construções AST requeridas pelo objetivo do exercício.",
            ),
            GradingRubricDTO(
                criterion="Qualidade", score=style_ratio, weight=0.10,
                explanation=("Estrutura legível e sem problemas básicos." if not style_findings
                             else "; ".join(style_findings)),
            ),
        )
        score = round(sum(item.score * item.weight for item in rubric), 4)
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
            feedback=tuple(feedback), rubric=rubric,
        )

    @staticmethod
    def _style_findings(tree: ast.AST) -> tuple[str, ...]:
        findings: list[str] = []
        long_functions = [
            node.name for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and getattr(node, "end_lineno", node.lineno) - node.lineno > 60
        ]
        if long_functions:
            findings.append("Funções demasiado longas: " + ", ".join(long_functions[:3]))
        vague = sum(
            1 for node in ast.walk(tree)
            if isinstance(node, ast.Name) and node.id in {"x", "y", "tmp", "foo", "bar"}
        )
        if vague > 5:
            findings.append("Existem vários nomes pouco descritivos")
        return tuple(findings)
