from dataclasses import dataclass

import pytest

from aprendix.application.contracts import SnippetRequestDTO
from aprendix.application.snippet_analysis import SnippetAnalyzer


@dataclass(frozen=True)
class GoldenCase:
    id: str
    source: str
    constructs: tuple[str, ...] = ()
    diagnostic: str = ""
    security: str = ""


TARGETED = (
    GoldenCase("assignment", "value: int = 3", ("AnnAssign",)),
    GoldenCase("function", "def add(a, b):\n    return a + b", ("FunctionDef", "Return")),
    GoldenCase("closure", "def outer(x):\n    def inner(y):\n        return x + y\n    return inner", ("FunctionDef",)),
    GoldenCase("nonlocal", "def outer():\n    x = 0\n    def inner():\n        nonlocal x\n        x += 1\n    return inner", ("Nonlocal",)),
    GoldenCase("global", "count = 0\ndef tick():\n    global count\n    count += 1", ("Global",)),
    GoldenCase("class", "class Child(Base):\n    def run(self):\n        return self.value", ("ClassDef",), "name.undefined"),
    GoldenCase("decorator", "@cache\ndef compute(x):\n    return x", ("FunctionDef",), "name.undefined"),
    GoldenCase("async", "async def load(stream):\n    async for item in stream:\n        await item", ("AsyncFunctionDef", "AsyncFor")),
    GoldenCase("unreachable", "def f():\n    return 1\n    print(2)", ("Return",), "flow.unreachable"),
    GoldenCase("bare-except", "try:\n    work()\nexcept:\n    pass", ("Try",), "except.bare"),
    GoldenCase("mutable-default", "def append(value, items=[]):\n    items.append(value)\n    return items", ("FunctionDef",), "default.mutable"),
    GoldenCase("eval", "value = eval('1 + 1')", ("Call",), security="security.dynamic_eval"),
    GoldenCase("exec", "exec('x = 1')", ("Call",), security="security.dynamic_exec"),
    GoldenCase("filesystem", "data = open('local.txt').read()", ("Call",), security="security.filesystem"),
    GoldenCase("undefined", "result = missing + 1", ("BinOp",), "name.undefined"),
    GoldenCase("shadow", "list = [1, 2]", ("List",), "name.shadow_builtin"),
    GoldenCase("comprehension", "squares = [x * x for x in range(5)]", ("ListComp",)),
    GoldenCase("match", "match status:\n    case 200:\n        result = 'ok'\n    case _:\n        result = 'error'", ("Match",), "name.undefined"),
    GoldenCase("recursion", "def factorial(n):\n    return 1 if n <= 1 else n * factorial(n - 1)", ("FunctionDef",)),
    GoldenCase(
        "capital",
        "import math\ndef capital(initial, rate, years):\n    return initial * math.pow(1 + rate / 100, years)",
        ("Import", "FunctionDef"),
    ),
)

GENERATED = tuple(
    GoldenCase(
        f"branch-{index:02d}",
        f"def classify_{index}(value: int) -> str:\n"
        "    if value < 0:\n"
        "        return 'negative'\n"
        "    if value == 0:\n"
        "        return 'zero'\n"
        "    return 'positive'",
        ("FunctionDef", "If", "Return"),
    )
    for index in range(30)
)

GOLDEN_CORPUS = TARGETED + GENERATED


def test_golden_corpus_contains_fifty_distinct_static_cases() -> None:
    assert len(GOLDEN_CORPUS) == 50
    assert len({item.id for item in GOLDEN_CORPUS}) == 50


@pytest.mark.parametrize("case", GOLDEN_CORPUS, ids=lambda case: case.id)
def test_golden_static_analysis(case: GoldenCase) -> None:
    result = SnippetAnalyzer().analyze(SnippetRequestDTO(
        text=case.source,
        language_hint="python",
    ))
    assert set(case.constructs) <= set(result.constructs)
    assert result.analysis_truncated is False
    assert result.elapsed_ms < 1_500
    assert "não executou" in result.summary
    if case.diagnostic:
        assert case.diagnostic in {item.code for item in result.diagnostics}
    if case.security:
        assert case.security in {item.code for item in result.security_findings}
