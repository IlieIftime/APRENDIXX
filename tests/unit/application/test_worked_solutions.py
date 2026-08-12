from aprendix.application.worked_solutions import (
    explain_reference_solution,
    solution_fingerprint,
)


def test_reference_explanation_is_structural_and_fingerprint_tracks_tests():
    source = "def par(numero):\n    return numero % 2 == 0"
    explanation = explain_reference_solution(source)

    assert "par(numero)" in explanation
    assert "retorno" in explanation
    assert "não a única resposta" in explanation
    assert solution_fingerprint(source, ("assert par(2)",)) != solution_fingerprint(
        source, ("assert par(4)",)
    )
