"""Deterministic prompt cleanup and lightweight local IDE diagnostics."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass


_encoding = re.compile(r"^\s*#\s*[-*]+\s*coding\s*[:=]\s*[-\w.]+\s*[-*]*\s*$", re.I)


def sanitize_exercise_prompt(value: str) -> str:
    """Remove extractor artefacts without rewriting the exercise's meaning."""

    value = value.replace("\ufeff", "").replace("\x00", "")
    value = "".join(char for char in value if char in "\n\t" or ord(char) >= 32)
    lines = [line.rstrip() for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    lines = [line for line in lines if not _encoding.match(line)]
    value = "\n".join(lines)
    # PDF line wrapping commonly leaves a hyphen between two word fragments.
    value = re.sub(r"(?<=[A-Za-zÀ-ÿ])-\s*\n\s*(?=[a-zà-ÿ])", "", value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


@dataclass(frozen=True, slots=True)
class Diagnostic:
    line: int
    column: int
    severity: str
    message: str


def diagnose_python(source: str) -> tuple[Diagnostic, ...]:
    """Return bounded syntax and maintainability diagnostics, fully offline."""

    issues: list[Diagnostic] = []
    for number, line in enumerate(source.splitlines(), start=1):
        leading = line[:len(line) - len(line.lstrip())]
        if "\t" in leading and " " in leading:
            issues.append(Diagnostic(number, 1, "erro", "Indentação mistura tabs e espaços."))
        elif "\t" in leading:
            issues.append(Diagnostic(number, 1, "aviso", "Usa quatro espaços em vez de tabs."))
        if line.rstrip() != line:
            issues.append(Diagnostic(number, len(line.rstrip()) + 1, "info", "Espaços no fim da linha."))
        if len(line) > 100:
            issues.append(Diagnostic(number, 101, "info", "Linha longa; considera dividi-la."))
    try:
        tree = ast.parse(source or "\n")
    except (SyntaxError, IndentationError) as exc:
        issues.insert(0, Diagnostic(
            int(exc.lineno or 1), int(exc.offset or 1), "erro",
            (exc.msg or "Sintaxe inválida").replace("unexpected indent", "indentação inesperada"),
        ))
        return tuple(issues[:30])
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            issues.append(Diagnostic(node.lineno, node.col_offset + 1, "aviso", "Evita `except:` genérico; indica a exceção esperada."))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = (*node.args.defaults, *node.args.kw_defaults)
            if any(isinstance(item, (ast.List, ast.Dict, ast.Set)) for item in defaults if item is not None):
                issues.append(Diagnostic(node.lineno, node.col_offset + 1, "aviso", "Argumento mutável por omissão conserva estado entre chamadas."))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            issues.append(Diagnostic(node.lineno, node.col_offset + 1, "aviso", f"`{node.func.id}` executa texto como código e é bloqueado no sandbox."))
    return tuple(issues[:30])
