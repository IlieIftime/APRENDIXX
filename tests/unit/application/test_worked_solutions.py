from aprendix.application.worked_solutions import (
    build_reference_walkthrough,
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


def test_reference_walkthrough_is_static_and_keeps_trace_separate_from_traceback():
    source = (
        "def acumulado(inicial, taxa, anos):\n"
        "    valor = inicial\n"
        "    for _ano in range(anos):\n"
        "        valor *= 1 + taxa / 100\n"
        "    return round(valor, 2)"
    )
    walkthrough = build_reference_walkthrough(
        source, ("assert acumulado(1500, 2, 1) == 1530.0",)
    )

    assert any("entra na função acumulado" in item for item in walkthrough.steps)
    assert any("percorre range(anos)" in item for item in walkthrough.steps)
    assert any("devolvendo round(valor, 2)" in item for item in walkthrough.steps)
    assert walkthrough.expected_behaviour == (
        "acumulado(1500, 2, 1) -> 1530.0",
    )
    rendered = walkthrough.render()
    assert "Traço estrutural" in rendered
    assert "Comportamento esperado" in rendered
    assert "Traceback" not in rendered


def test_reference_walkthrough_never_evaluates_assertion_arguments(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("runtime execution is forbidden")

    monkeypatch.setattr("builtins.eval", forbidden)
    monkeypatch.setattr("builtins.exec", forbidden)
    result = build_reference_walkthrough(
        "def identidade(valor):\n    return valor",
        ("assert identidade('ok') == 'ok'",),
    )

    assert result.expected_behaviour == ("identidade('ok') -> 'ok'",)
