from aprendix.application.contracts import (
    GradingTestOutcomeDTO,
    SmartCorrectionResponseDTO,
)
from aprendix.application.learning_session import (
    AssistanceStage,
    assistance_for_attempt,
    render_microtheory,
)


def _failed_correction(*, syntax_valid=True):
    return SmartCorrectionResponseDTO(
        score=0.25,
        status="failed" if syntax_valid else "syntax_error",
        syntax_valid=syntax_valid,
        policy_safe=True,
        test_outcomes=(
            GradingTestOutcomeDTO(
                name="Teste 1", passed=False, visibility="public", message="falhou"
            ),
            GradingTestOutcomeDTO(
                name="Caso oculto 2", passed=False, visibility="hidden", message="segredo"
            ),
        ),
        feedback=("Revê a condição.",),
    )


def test_help_ladder_progresses_without_disclosing_hidden_assertions():
    correction = _failed_correction()

    first = assistance_for_attempt(correction, failed_attempts=1, concepts=("funções",))
    fourth = assistance_for_attempt(
        correction,
        failed_attempts=4,
        concepts=("funções",),
        theory_title="Validação",
        worked_example="def positivo(valor): return valor > 0",
    )

    assert first.stage is AssistanceStage.LOCATION
    assert fourth.stage is AssistanceStage.ANALOGOUS_EXAMPLE
    assert "Validação" in fourth.worked_example
    assert "def positivo" in fourth.worked_example
    assert not any("segredo" in line for line in (*first.guidance, *fourth.guidance))


def test_assessment_caps_help_before_strategy_or_example():
    decision = assistance_for_attempt(
        _failed_correction(), failed_attempts=12,
        worked_example="não deve aparecer", evaluation_locked=True,
    )

    assert decision.stage is AssistanceStage.CONCEPT
    assert decision.worked_example == ""


def test_microtheory_provides_prediction_to_practice_bridge():
    rendered = render_microtheory(
        "Conversão segura", "Valida antes de converter.", "inteiro_ou('7') devolve 7."
    )

    assert rendered.startswith("Microteoria · Conversão segura")
    assert "Exemplo orientador" in rendered
    assert "Antes de programar" in rendered
    assert "caso-limite" in rendered
