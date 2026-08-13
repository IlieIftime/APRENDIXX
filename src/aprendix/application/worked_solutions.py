"""Validation metadata and readable explanations for trusted reference code."""

from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReferenceWalkthrough:
    """A bounded, static explanation of trusted reference code.

    ``steps`` describe control flow without pretending that the code has been
    executed. ``expected_behaviour`` is extracted only from literal public
    assertions, so no user or catalogue code is evaluated while building the
    learning document.
    """

    steps: tuple[str, ...]
    expected_behaviour: tuple[str, ...]

    def render(self) -> str:
        sections: list[str] = []
        if self.steps:
            sections.append(
                "Traço estrutural\n" + "\n".join(
                    f"{index}. {step}" for index, step in enumerate(self.steps, 1)
                )
            )
        if self.expected_behaviour:
            sections.append(
                "Comportamento esperado\n" + "\n".join(self.expected_behaviour)
            )
        return "\n\n".join(sections)


def solution_fingerprint(source: str, tests: tuple[str, ...]) -> str:
    payload = json.dumps(
        {"source": source, "tests": tests}, ensure_ascii=False,
        sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def explain_reference_solution(source: str) -> str:
    """Explain structural decisions without executing or changing the source."""

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return "A solução de referência não tem uma estrutura Python válida."
    lines: list[str] = []
    functions = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    classes = [node for node in tree.body if isinstance(node, ast.ClassDef)]
    assignments = sum(isinstance(node, (ast.Assign, ast.AnnAssign)) for node in ast.walk(tree))
    conditions = sum(isinstance(node, ast.If) for node in ast.walk(tree))
    loops = sum(isinstance(node, (ast.For, ast.While)) for node in ast.walk(tree))
    returns = sum(isinstance(node, ast.Return) for node in ast.walk(tree))
    if functions:
        lines.append(
            "Define o contrato através de "
            + ", ".join(f"{node.name}({', '.join(arg.arg for arg in node.args.args)})" for node in functions)
            + "."
        )
    if classes:
        lines.append(
            "Organiza estado e comportamento na(s) classe(s): "
            + ", ".join(node.name for node in classes) + "."
        )
    if assignments:
        lines.append(f"Usa {assignments} atribuição(ões) para tornar valores intermédios observáveis.")
    if conditions:
        lines.append(f"Aplica {conditions} decisão(ões) para separar casos do contrato.")
    if loops:
        lines.append(f"Percorre os dados com {loops} ciclo(s), mantendo a transformação local.")
    if returns:
        lines.append(f"Termina o cálculo através de {returns} retorno(s) explícito(s).")
    if not lines:
        lines.append("Resolve o contrato com uma sequência direta de expressões locais.")
    lines.append(
        "Esta é uma implementação validada, não a única resposta possível. Compara decisões e testes, não apenas texto."
    )
    return "\n".join(lines)


def build_reference_walkthrough(
    source: str, tests: tuple[str, ...] = (), *, max_steps: int = 80,
) -> ReferenceWalkthrough:
    """Build an execution-oriented walkthrough without running Python code.

    This deliberately uses the term *structural trace*. Concrete runtime
    values belong to the isolated debugger. A traceback is an exception report
    and is therefore never fabricated for a successful reference solution.
    """

    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return ReferenceWalkthrough(
            steps=("A solução não pôde ser convertida numa árvore Python válida.",),
            expected_behaviour=_literal_expected_behaviour(tests),
        )

    steps: list[str] = []

    def add(node: ast.AST, message: str) -> None:
        if len(steps) >= max(1, max_steps):
            return
        line = int(getattr(node, "lineno", 0) or 0)
        prefix = f"Linha {line}: " if line else ""
        steps.append(prefix + message)

    for node in ast.walk(tree):
        if len(steps) >= max(1, max_steps):
            break
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parameters = ", ".join(argument.arg for argument in node.args.args)
            add(node, f"entra na função {node.name}({parameters}) e cria o respetivo âmbito local.")
        elif isinstance(node, ast.ClassDef):
            add(node, f"define a classe {node.name} e prepara os seus atributos e métodos.")
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            targets = _assignment_targets(node)
            expression = _assignment_expression(node)
            rendered = ", ".join(targets) or "o destino indicado"
            add(
                node,
                f"calcula {expression} e atualiza {rendered}."
                if expression else f"atualiza {rendered}.",
            )
        elif isinstance(node, ast.For):
            add(
                node,
                f"percorre {_safe_unparse(node.iter)} atribuindo cada elemento a "
                f"{_safe_unparse(node.target)}.",
            )
        elif isinstance(node, ast.While):
            add(node, f"repete o bloco enquanto {_safe_unparse(node.test)} for verdadeiro.")
        elif isinstance(node, ast.If):
            add(node, f"avalia {_safe_unparse(node.test)} e escolhe um dos ramos.")
        elif isinstance(node, ast.Try):
            add(node, "executa um bloco protegido e encaminha apenas as exceções declaradas.")
        elif isinstance(node, ast.Return):
            result = _safe_unparse(node.value) if node.value is not None else "None"
            add(node, f"termina a função devolvendo {result}.")
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            function = _safe_unparse(node.value.func)
            if function == "print":
                add(node, "envia uma linha para o output observável.")

    if not steps:
        steps.append("Avalia as expressões pela ordem em que aparecem no módulo.")
    return ReferenceWalkthrough(
        steps=tuple(steps),
        expected_behaviour=_literal_expected_behaviour(tests),
    )


def _safe_unparse(node: ast.AST | None, *, limit: int = 180) -> str:
    if node is None:
        return ""
    try:
        rendered = ast.unparse(node)
    except (AttributeError, ValueError, TypeError):
        return type(node).__name__
    rendered = " ".join(rendered.split())
    return rendered if len(rendered) <= limit else rendered[: limit - 1].rstrip() + "…"


def _assignment_targets(node: ast.Assign | ast.AnnAssign | ast.AugAssign) -> tuple[str, ...]:
    raw: tuple[ast.AST, ...]
    if isinstance(node, ast.Assign):
        raw = tuple(node.targets)
    else:
        raw = (node.target,)
    return tuple(_safe_unparse(target) for target in raw)


def _assignment_expression(node: ast.Assign | ast.AnnAssign | ast.AugAssign) -> str:
    if isinstance(node, ast.AugAssign):
        return _safe_unparse(node)
    return _safe_unparse(node.value)


def _literal_expected_behaviour(
    tests: tuple[str, ...], *, limit: int = 8,
) -> tuple[str, ...]:
    """Extract safe call/result examples from literal equality assertions."""

    examples: list[str] = []
    for test_source in tests:
        try:
            test_tree = ast.parse(test_source)
        except (SyntaxError, ValueError):
            continue
        for node in ast.walk(test_tree):
            if not isinstance(node, ast.Assert) or not isinstance(node.test, ast.Compare):
                continue
            comparison = node.test
            if (
                len(comparison.ops) != 1
                or not isinstance(comparison.ops[0], ast.Eq)
                or len(comparison.comparators) != 1
                or not isinstance(comparison.left, ast.Call)
            ):
                continue
            try:
                for argument in (*comparison.left.args, *comparison.left.keywords):
                    value = argument.value if isinstance(argument, ast.keyword) else argument
                    ast.literal_eval(value)
                ast.literal_eval(comparison.comparators[0])
            except (ValueError, TypeError):
                continue
            rendered = (
                f"{_safe_unparse(comparison.left)} -> "
                f"{_safe_unparse(comparison.comparators[0])}"
            )
            if rendered not in examples:
                examples.append(rendered)
            if len(examples) >= limit:
                return tuple(examples)
    return tuple(examples)
