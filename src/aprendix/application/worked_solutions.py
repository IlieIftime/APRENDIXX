"""Validation metadata and readable explanations for trusted reference code."""

from __future__ import annotations

import ast
import hashlib
import json


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
