import builtins

from aprendix.application.contracts import SnippetAction, SnippetRequestDTO
from aprendix.application.snippet_analysis import AnalysisBudget, SnippetAnalyzer

DEEP_SAMPLE = """\
import math

class CapitalCalculator:
    def __init__(self, initial: float):
        self.initial = initial

    def accumulated(self, rates: tuple[float, ...], years: int) -> list[float]:
        values = []
        for year in range(1, years + 1):
            for rate in rates:
                values.append(self.initial * math.pow(1 + rate / 100, year))
        return values
        print('unreachable')

def broken_reference():
    return missing_name
"""


def test_deep_static_report_exposes_requested_structures() -> None:
    result = SnippetAnalyzer().analyze(SnippetRequestDTO(
        text=DEEP_SAMPLE,
        action=SnippetAction.FIND_PROBLEMS,
    ))
    assert {item.name for item in result.functions} >= {"__init__", "accumulated", "broken_reference"}
    assert result.classes[0].name == "CapitalCalculator"
    assert {item.name for item in result.symbols} >= {"math", "values", "year", "rate"}
    assert any(item.inferred_type == "list" for item in result.type_facts)
    assert any(item.code == "name.undefined" and "missing_name" in item.message for item in result.diagnostics)
    assert any(item.code == "flow.unreachable" for item in result.diagnostics)
    assert any(item.callee == "math.pow" for item in result.call_edges)
    assert any(item.scope.endswith("accumulated") and item.cyclomatic >= 3 for item in result.complexity_findings)
    assert result.cfg_blocks and any(item.successors for item in result.cfg_blocks)
    assert "ZeroDivisionError" in result.possible_exceptions
    assert result.node_count > 30


def test_analysis_never_executes_eval_or_exec(monkeypatch) -> None:
    request = SnippetRequestDTO(
        text="payload = 'raise RuntimeError()'\nvalue = eval(payload)\nexec(payload)",
        action=SnippetAction.FIND_PROBLEMS,
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("user input was executed")

    monkeypatch.setattr(builtins, "eval", forbidden)
    monkeypatch.setattr(builtins, "exec", forbidden)
    result = SnippetAnalyzer().analyze(request)
    assert {item.code for item in result.security_findings} >= {
        "security.dynamic_eval", "security.dynamic_exec",
    }
    assert "não executou" in result.summary


def test_actions_produce_materially_distinct_reports() -> None:
    source = "def double(value: int) -> int:\n    return value * 2"
    outputs = {
        action: SnippetAnalyzer().analyze(SnippetRequestDTO(text=source, action=action))
        for action in (
            SnippetAction.EXPLAIN,
            SnippetAction.FIND_PROBLEMS,
            SnippetAction.CREATE_TESTS,
            SnippetAction.VISUALIZE,
            SnippetAction.LINK_COURSE,
        )
    }
    assert len({item.action_result for item in outputs.values()}) == len(outputs)
    assert outputs[SnippetAction.CREATE_TESTS].test_suggestions
    assert outputs[SnippetAction.VISUALIZE].cfg_blocks


def test_incomplete_python_returns_partial_symbols_and_location() -> None:
    result = SnippetAnalyzer().analyze(SnippetRequestDTO(
        text="def total(values)\n    result = 0",
        language_hint="python",
    ))
    assert result.diagnostics[0].code == "syntax.invalid"
    assert any(item.name == "total" for item in result.symbols)
    assert result.confidence < .7


def test_ast_depth_budget_stops_deep_passes() -> None:
    analyzer = SnippetAnalyzer(budget=AnalysisBudget(max_depth=10))
    result = analyzer.analyze(SnippetRequestDTO(
        text="value = [[[[[[[[[[[1]]]]]]]]]]]",
        language_hint="python",
    ))
    assert result.analysis_truncated is True
    assert result.diagnostics[0].code == "budget.ast"


def test_capital_accumulation_example_reports_formula_loops_and_stdout() -> None:
    source = """\
import math
ano_inicio = 2020
anos = 3
inicial = 1500
taxas = (2, 2.5, 3)
for numero_ano in range(1, anos + 1):
    print(ano_inicio + numero_ano, end='')
    for taxa in taxas:
        acumulado = inicial * math.pow(1 + taxa / 100, numero_ano)
        print(f'{acumulado:.2f}', end='')
    print()
"""
    result = SnippetAnalyzer().analyze(SnippetRequestDTO(
        text=source,
        action=SnippetAction.VISUALIZE,
    ))
    assert result.imports == ("math",)
    assert {item.callee for item in result.call_edges} >= {"range", "math.pow", "print"}
    assert {item.name for item in result.symbols} >= {
        "ano_inicio", "anos", "inicial", "taxas", "numero_ano", "taxa", "acumulado",
    }
    assert result.complexity_time == "O(n^2)"
    assert any("stdout" in item for item in result.outputs)
    assert any(block.kind == "For" and len(block.successors) == 2 for block in result.cfg_blocks)
