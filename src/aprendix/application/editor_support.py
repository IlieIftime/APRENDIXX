"""Deterministic prompt cleanup and lightweight local IDE diagnostics."""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from difflib import SequenceMatcher


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
    code: str = ""
    quick_fix: str = ""


def explain_runtime_error(error_type: str | None, message: str | None) -> str:
    """Translate a Python failure into an actionable, non-solution hint."""

    name = (error_type or "Erro de execução").strip()
    detail = (message or "").strip().splitlines()[-1][:500]
    guidance = {
        "NameError": "O nome ainda não existe neste ponto. Confirma a grafia, o âmbito e a ordem de atribuição.",
        "TypeError": "Uma operação recebeu um tipo ou número de argumentos incompatível. Observa os valores e o contrato da função.",
        "IndexError": "O índice está fora dos limites atuais. Verifica o tamanho da sequência e as fronteiras do ciclo.",
        "KeyError": "A chave não está presente no mapa. Confirma a origem dos dados ou trata explicitamente a ausência.",
        "ZeroDivisionError": "O denominador tornou-se zero. Identifica que entrada produz esse estado e define a política adequada.",
        "AttributeError": "O objeto não expõe esse atributo. Confirma o seu tipo real e a interface esperada.",
        "ValueError": "O tipo é aceite, mas o valor não respeita o domínio esperado. Valida a entrada antes da operação.",
        "RecursionError": "A recursão não atingiu um caso base. Revê a condição de paragem e a redução do problema.",
        "SyntaxError": "O analisador não conseguiu construir a estrutura do programa. Começa pela linha indicada e pelos delimitadores anteriores.",
        "IndentationError": "Os blocos não têm uma indentação coerente. Usa quatro espaços e alinha instruções do mesmo bloco.",
    }.get(name, "Segue o último frame executado, observa os valores locais e reduz o caso até reproduzir a falha.")
    return f"{name}: {detail}\n\nComo investigar: {guidance}".strip()


def diagnose_python(source: str) -> tuple[Diagnostic, ...]:
    """Return bounded syntax and maintainability diagnostics, fully offline."""

    issues: list[Diagnostic] = []
    for number, line in enumerate(source.splitlines(), start=1):
        leading = line[:len(line) - len(line.lstrip())]
        if "\t" in leading and " " in leading:
            issues.append(Diagnostic(number, 1, "erro", "Indentação mistura tabs e espaços.", "indent.mixed", "Converter indentação para quatro espaços"))
        elif "\t" in leading:
            issues.append(Diagnostic(number, 1, "aviso", "Usa quatro espaços em vez de tabs.", "indent.tabs", "Converter indentação para quatro espaços"))
        if line.rstrip() != line:
            issues.append(Diagnostic(number, len(line.rstrip()) + 1, "info", "Espaços no fim da linha.", "whitespace.trailing", "Remover espaços finais"))
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
            issues.append(Diagnostic(node.lineno, node.col_offset + 1, "aviso", "Evita `except:` genérico; indica a exceção esperada.", "except.bare", "Substituir por `except Exception:`"))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = (*node.args.defaults, *node.args.kw_defaults)
            if any(isinstance(item, (ast.List, ast.Dict, ast.Set)) for item in defaults if item is not None):
                issues.append(Diagnostic(node.lineno, node.col_offset + 1, "aviso", "Argumento mutável por omissão conserva estado entre chamadas.", "default.mutable", "Usar `None` e criar o valor dentro da função"))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"eval", "exec"}:
            issues.append(Diagnostic(node.lineno, node.col_offset + 1, "aviso", f"`{node.func.id}` executa texto como código e é bloqueado no sandbox."))
    return tuple(issues[:30])


def apply_quick_fix(source: str, diagnostic: Diagnostic) -> tuple[str, bool]:
    """Apply one conservative fix without rewriting user program structure."""

    lines = source.splitlines(keepends=True)
    index = diagnostic.line - 1
    if not 0 <= index < len(lines):
        return source, False
    original = lines[index]
    ending = "\r\n" if original.endswith("\r\n") else "\n" if original.endswith("\n") else ""
    body = original[:-len(ending)] if ending else original
    changed = body
    if diagnostic.code in {"indent.mixed", "indent.tabs"}:
        leading = body[:len(body) - len(body.lstrip(" \t"))]
        changed = leading.expandtabs(4) + body[len(leading):]
    elif diagnostic.code == "whitespace.trailing":
        changed = body.rstrip(" \t")
    elif diagnostic.code == "except.bare":
        changed = re.sub(r"^(\s*)except\s*:\s*$", r"\1except Exception:", body)
    else:
        return source, False
    if changed == body:
        return source, False
    lines[index] = changed + ending
    return "".join(lines), True


def apply_safe_quick_fixes(source: str) -> tuple[str, int]:
    """Apply every semantics-preserving quick fix currently available."""

    count = 0
    # Re-diagnose after every edit so line references can never become stale.
    while count < 100:
        for diagnostic in diagnose_python(source):
            updated, applied = apply_quick_fix(source, diagnostic)
            if applied:
                source, count = updated, count + 1
                break
        else:
            break
    return source, count


def format_python(source: str) -> str:
    """Apply conservative whitespace formatting without destroying comments."""
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    lines, blank_count = [], 0
    for raw in normalized.split("\n"):
        leading = raw[:len(raw) - len(raw.lstrip(" \t"))]
        expanded = leading.expandtabs(4) + raw[len(leading):].rstrip()
        if not expanded.strip():
            blank_count += 1
            if blank_count > 2:
                continue
            expanded = ""
        else:
            blank_count = 0
        lines.append(expanded)
    result = "\n".join(lines).strip("\n") + "\n"
    ast.parse(result)
    return result


def organize_imports(source: str) -> str:
    """Sort the leading import block; imports elsewhere keep their semantics."""
    ast.parse(source or "\n")
    lines = source.splitlines()
    start = 1 if lines and lines[0].startswith("#!") else 0
    while start < len(lines) and (_encoding.match(lines[start]) or not lines[start].strip()):
        start += 1
    end = start
    while end < len(lines) and (
        lines[end].startswith("import ") or lines[end].startswith("from ")
        or not lines[end].strip()
    ):
        end += 1
    imports = sorted({line.strip() for line in lines[start:end] if line.strip()}, key=str.casefold)
    if not imports:
        return source
    rebuilt = lines[:start] + imports + ([""] if end < len(lines) else []) + lines[end:]
    return "\n".join(rebuilt).rstrip() + ("\n" if source.endswith("\n") else "")


def find_replace(
    source: str, needle: str, replacement: str, *, case_sensitive: bool = True,
    whole_word: bool = False,
) -> tuple[str, int]:
    if not needle:
        raise ValueError("O texto a procurar não pode estar vazio.")
    flags = 0 if case_sensitive else re.IGNORECASE
    pattern = re.escape(needle)
    if whole_word:
        pattern = rf"(?<!\w){pattern}(?!\w)"
    return re.subn(pattern, lambda _match: replacement, source, flags=flags)


def matching_delimiter(source: str, cursor: int) -> int | None:
    if not 0 <= cursor < len(source) or source[cursor] not in "()[]{}":
        return None
    pairs = {"(": ")", "[": "]", "{": "}"}
    reverse = {")": "(", "]": "[", "}": "{"}
    opening = source[cursor] in pairs
    target = pairs.get(source[cursor], reverse.get(source[cursor]))
    direction, depth = (1, 0) if opening else (-1, 0)
    for index in range(cursor, len(source) if opening else -1, direction):
        char = source[index]
        if char == source[cursor]:
            depth += 1
        elif char == target:
            depth -= 1
            if depth == 0:
                return index
    return None


def analyze_complexity(source: str) -> dict[str, object]:
    tree = ast.parse(source or "\n")
    loops = sum(
        isinstance(node, (ast.For, ast.While, ast.comprehension))
        for node in ast.walk(tree)
    )
    functions = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    recursive = any(
        isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
        and call.func.id == function.name
        for function in functions for call in ast.walk(function)
    )
    max_loop_depth = 0

    def visit(node, depth=0):
        nonlocal max_loop_depth
        next_depth = depth + int(isinstance(node, (ast.For, ast.While, ast.comprehension)))
        max_loop_depth = max(max_loop_depth, next_depth)
        for child in ast.iter_child_nodes(node):
            visit(child, next_depth)

    visit(tree)
    time_class = (
        "O(?)" if recursive else "O(1)" if max_loop_depth == 0
        else "O(n)" if max_loop_depth == 1 else f"O(n^{max_loop_depth})"
    )
    containers = sum(
        isinstance(node, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp))
        for node in ast.walk(tree)
    )
    return {
        "time": time_class, "space": "O(n)" if containers else "O(1)",
        "loops": loops, "max_loop_depth": max_loop_depth, "recursive": recursive,
        "note": "Estimativa estrutural; confirma com entradas representativas.",
    }


def compare_solutions(left: str, right: str) -> dict[str, object]:
    left_tree, right_tree = ast.parse(left or "\n"), ast.parse(right or "\n")
    left_nodes = {type(node).__name__ for node in ast.walk(left_tree)}
    right_nodes = {type(node).__name__ for node in ast.walk(right_tree)}
    return {
        "text_similarity": SequenceMatcher(None, left, right).ratio(),
        "shared_constructs": tuple(sorted(left_nodes & right_nodes)),
        "only_left": tuple(sorted(left_nodes - right_nodes)),
        "only_right": tuple(sorted(right_nodes - left_nodes)),
        "left_complexity": analyze_complexity(left),
        "right_complexity": analyze_complexity(right),
    }
