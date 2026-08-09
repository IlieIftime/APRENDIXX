from aprendix.application.contracts import DebugBreakpointDTO, DebugRequestDTO
from aprendix.infrastructure.debugger import IsolatedPythonDebugger


def test_debugger_captures_breakpoint_watches_stack_and_coverage() -> None:
    result = IsolatedPythonDebugger().debug(DebugRequestDTO(
        source_code="total = 0\nfor n in range(4):\n    total += n\nprint(total)",
        breakpoints=(DebugBreakpointDTO(line=3, condition="n == 2"),),
        watches=("n", "total"),
    ))
    assert result.status == "completed"
    assert result.stdout.strip() == "6"
    assert result.token_verified is True
    assert result.memory_limit_enforced is True
    assert result.coverage_percent == 100
    hit = next(frame for frame in result.frames if frame.breakpoint_hit)
    assert hit.line == 3
    assert hit.watches == {"n": "2", "total": "1"}


def test_debugger_step_limit_stops_infinite_loop_without_host_crash() -> None:
    result = IsolatedPythonDebugger().debug(DebugRequestDTO(
        source_code="n = 0\nwhile True:\n    n += 1", max_steps=25,
    ))
    assert result.status == "step_limit"
    assert len(result.frames) == 25


def test_debugger_rejects_imports_and_unsafe_watch_calls() -> None:
    debugger = IsolatedPythonDebugger()
    blocked = debugger.debug(DebugRequestDTO(source_code="import socket\nprint('x')"))
    assert blocked.status == "rejected"
    try:
        debugger.debug(DebugRequestDTO(source_code="x = 2", watches=("open('x')",)))
    except ValueError as exc:
        assert "bloqueada" in str(exc)
    else:
        raise AssertionError("unsafe watch should have been rejected")


def test_debugger_does_not_call_user_repr_while_inspecting() -> None:
    result = IsolatedPythonDebugger().debug(DebugRequestDTO(
        source_code=(
            "class Caixa:\n"
            "    def __repr__(self):\n"
            "        while True:\n"
            "            pass\n"
            "valor = Caixa()\n"
            "print('ok')"
        ),
        watches=("valor",), max_steps=100,
    ))
    assert result.status == "completed"
    assert any(frame.watches.get("valor") == "<Caixa>" for frame in result.frames)
