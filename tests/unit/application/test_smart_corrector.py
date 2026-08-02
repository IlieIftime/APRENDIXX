"""POO correction policy and isolated execution tests."""

from aprendix.application.contracts import GradingTestCaseDTO, SmartCorrectionRequestDTO
from aprendix.application.smart_corrector import SmartCorrector
from aprendix.infrastructure.grading import IsolatedGradingExecutor, OopGradingPolicy


def corrector():
    return SmartCorrector(OopGradingPolicy(), IsolatedGradingExecutor())


def test_oop_solution_with_init_passes_isolated_test() -> None:
    response = corrector().correct(SmartCorrectionRequestDTO(
        source_code="class Counter:\n    def __init__(self, value):\n        self.value = value\n    def add(self, n):\n        return self.value + n",
        tests=(GradingTestCaseDTO(
            name="soma", code="counter = Counter(2)\nassert counter.add(3) == 5"
        ),),
        required_constructs=("ClassDef", "FunctionDef"),
    ))
    assert response.status == "passed"
    assert response.score == 1.0


def test_corrector_rejects_dunder_introspection() -> None:
    response = corrector().correct(SmartCorrectionRequestDTO(
        source_code="value = (1).__class__",
    ))
    assert response.status == "rejected"
    assert response.policy_safe is False


def test_corrector_reports_syntax_error_without_execution() -> None:
    response = corrector().correct(SmartCorrectionRequestDTO(source_code="class Broken("))
    assert response.status == "syntax_error"
    assert response.score == 0


def test_corrector_never_marks_an_untested_solution_as_passed() -> None:
    response = corrector().correct(SmartCorrectionRequestDTO(source_code="value = 2"))
    assert response.status == "failed"
    assert response.score < 1
    assert "Não existem testes" in response.feedback[0]
