from aprendix.application.contracts import (
    DebugFrameDTO, DebugSessionDTO, GradingTestOutcomeDTO, SmartCorrectionResponseDTO,
)
from aprendix.application.pedagogy_tools import (
    profile_execution, staged_hints, visualize_structures,
)


def test_visualizer_and_profiler_use_safe_trace_values() -> None:
    session = DebugSessionDTO(
        status="completed", duration_ms=12, coverage_percent=75,
        executed_lines=(1, 2, 3), token_verified=True,
        frames=(DebugFrameDTO(
            step=1, line=2, event="line", function="<module>", call_depth=0,
            locals={"matrix": "[[1, 2], [3, 4]]", "unsafe": "Widget()"},
        ),),
    )
    structures = visualize_structures(session)
    assert [(item.name, item.kind, item.shape) for item in structures] == [
        ("matrix", "matriz/tensor", (2, 2)),
    ]
    profile = profile_execution(session)
    assert profile.hottest_lines == ((2, 1),)
    assert profile.coverage_percent == 75


def test_hint_ladder_never_exposes_hidden_test_code() -> None:
    response = SmartCorrectionResponseDTO(
        score=0, status="failed", syntax_valid=True, policy_safe=True,
        test_outcomes=(GradingTestOutcomeDTO(
            name="Caso oculto 2", passed=False, message="genérico", visibility="hidden",
        ),),
    )
    hints = staged_hints(response, concepts=("invariantes",))
    assert len(hints) == 4
    assert "oculto" in hints[0]
    assert "genérico" not in " ".join(hints)
