from aprendix.application.contracts import (
    GradingTestOutcomeDTO,
    SmartCorrectionResponseDTO,
)
from aprendix.application.remediation import DiagnosticCode, diagnose_correction


def _correction(*, syntax=True, public=False, hidden=False, status="failed"):
    outcomes = []
    if public:
        outcomes.append(GradingTestOutcomeDTO(
            name="Caso público", passed=False, message="detalhe público", visibility="public"
        ))
    if hidden:
        outcomes.append(GradingTestOutcomeDTO(
            name="Caso oculto", passed=False, message="SEGREDO_OCULTO", visibility="hidden"
        ))
    return SmartCorrectionResponseDTO(
        score=0.4,
        status=status,
        syntax_valid=syntax,
        policy_safe=True,
        test_outcomes=tuple(outcomes),
        feedback=("Revê o resultado.",),
    )


def test_diagnosis_distinguishes_syntax_logic_and_edge_cases():
    syntax = diagnose_correction(
        _correction(syntax=False, status="syntax_error"), current_source="def x(:"
    )
    logic = diagnose_correction(
        _correction(public=True), current_source="def x(): return 1"
    )
    edge = diagnose_correction(
        _correction(hidden=True), current_source="def x(): return 1"
    )

    assert syntax.code is DiagnosticCode.SYNTAX
    assert logic.code is DiagnosticCode.LOGIC
    assert edge.code is DiagnosticCode.EDGE_CASE
    assert "SEGREDO_OCULTO" not in repr(edge)


def test_attempt_comparison_reports_score_and_syntax_progress():
    plan = diagnose_correction(
        _correction(public=True),
        current_source="def x():\n    return 1",
        previous_source="def x(:",
        previous_score=0.1,
    )

    assert "melhorou 30%" in plan.improvement
    assert "sintaxe passou a ser válida" in plan.improvement
    assert plan.mini_exercise.startswith("Mini-prática")
