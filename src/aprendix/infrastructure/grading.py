"""POO-capable AST policy and isolated child-process grading harness."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from collections.abc import Mapping

from aprendix.infrastructure.windows_job import WindowsJobLimit


class OopGradingPolicy:
    """Allow classes and safe magic methods while blocking host capabilities."""

    _blocked_nodes = (
        ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal,
        ast.AsyncFunctionDef, ast.Await, ast.YieldFrom,
    )
    _blocked_calls = {
        "open", "eval", "exec", "compile", "__import__", "getattr", "setattr",
        "delattr", "globals", "locals", "vars", "dir", "help", "breakpoint",
        "input", "memoryview",
    }
    _safe_dunders = {"__init__", "__str__", "__repr__", "__len__", "__eq__"}
    _blocked_attributes = {
        "__class__", "__bases__", "__mro__", "__subclasses__", "__globals__",
        "__code__", "__closure__", "__getattribute__", "__dict__", "__reduce__",
        "__reduce_ex__", "__builtins__",
    }

    def violations(self, source: str, *, trusted_test: bool = False) -> tuple[str, ...]:
        try:
            tree = ast.parse(source, mode="exec")
        except SyntaxError as exc:
            return (f"syntax_error:{exc.lineno}:{exc.offset}",)
        findings: set[str] = set()
        if sum(1 for _ in ast.walk(tree)) > 10_000:
            findings.add("A árvore AST excede o limite de complexidade.")
        for node in ast.walk(tree):
            if isinstance(node, self._blocked_nodes):
                findings.add(f"Construção bloqueada: {type(node).__name__}.")
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id in self._blocked_calls:
                    findings.add(f"Chamada bloqueada: {node.func.id}.")
            if isinstance(node, ast.Attribute):
                if node.attr.startswith("_") or node.attr in self._blocked_attributes:
                    findings.add(f"Atributo bloqueado: {node.attr}.")
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                if node.name.startswith("__") and node.name not in self._safe_dunders:
                    findings.add(f"Nome especial bloqueado: {node.name}.")
            if isinstance(node, ast.Name) and node.id.startswith("__"):
                findings.add(f"Nome especial bloqueado: {node.id}.")
        return tuple(sorted(findings))


_GRADER_RUNNER = r'''
import builtins
import json
import sys

payload = json.loads(sys.stdin.buffer.read())
output = []
limit = 8192

def limited_print(*items, sep=" ", end="\n", **_kwargs):
    text = sep.join(str(item) for item in items) + end
    current = sum(len(item) for item in output)
    if current < limit:
        output.append(text[:limit-current])

safe = {
    "__build_class__": builtins.__build_class__, "abs": abs, "all": all, "any": any,
    "bool": bool, "classmethod": classmethod, "dict": dict, "enumerate": enumerate,
    "Exception": Exception, "float": float, "frozenset": frozenset, "int": int,
    "isinstance": isinstance, "issubclass": issubclass, "len": len, "list": list,
    "map": map, "max": max, "min": min, "object": object, "pow": pow,
    "print": limited_print, "property": property, "range": range, "repr": repr,
    "reversed": reversed, "round": round, "set": set, "slice": slice,
    "sorted": sorted, "staticmethod": staticmethod, "str": str, "sum": sum,
    "super": super, "tuple": tuple, "type": type, "KeyError": KeyError,
    "ValueError": ValueError,
    "zip": zip,
}
namespace = {"__builtins__": safe, "__name__": "__main__"}
status = "passed"
message = "Teste concluído."
try:
    exec(compile(payload["source"], "<learner>", "exec"), namespace, namespace)
    exec(compile(payload["test"], "<trusted-test>", "exec"), namespace, namespace)
except AssertionError:
    status = "failed"
    message = "A asserção do teste não foi satisfeita."
except BaseException as exc:
    status = "error"
    message = (type(exc).__name__ + ": " + str(exc))[:1000]
sys.__stdout__.write(json.dumps({"status": status, "message": message}, ensure_ascii=True))
'''


def _evaluate_payload(payload: Mapping[str, str]) -> dict[str, str]:
    """Evaluate one already-policy-checked submission in a constrained namespace."""

    import builtins

    output: list[str] = []
    limit = 8_192

    def limited_print(*items: object, sep: str = " ", end: str = "\n", **_kwargs: object) -> None:
        text = sep.join(str(item) for item in items) + end
        current = sum(len(item) for item in output)
        if current < limit:
            output.append(text[: limit - current])

    safe = {
        "__build_class__": builtins.__build_class__, "abs": abs, "all": all,
        "any": any, "bool": bool, "classmethod": classmethod, "dict": dict,
        "enumerate": enumerate, "Exception": Exception, "float": float,
        "frozenset": frozenset, "int": int, "isinstance": isinstance,
        "issubclass": issubclass, "len": len, "list": list, "map": map,
        "max": max, "min": min, "object": object, "pow": pow,
        "print": limited_print, "property": property, "range": range,
        "repr": repr, "reversed": reversed, "round": round, "set": set,
        "slice": slice, "sorted": sorted, "staticmethod": staticmethod,
        "str": str, "sum": sum, "super": super, "tuple": tuple,
        "type": type, "KeyError": KeyError, "ValueError": ValueError, "zip": zip,
    }
    namespace = {"__builtins__": safe, "__name__": "__main__"}
    try:
        exec(compile(payload["source"], "<learner>", "exec"), namespace, namespace)
        exec(compile(payload["test"], "<trusted-test>", "exec"), namespace, namespace)
    except AssertionError:
        return {
            "status": "failed",
            "message": "A asserção do teste não foi satisfeita.",
        }
    except BaseException as exc:
        return {
            "status": "error",
            "message": (type(exc).__name__ + ": " + str(exc))[:1_000],
        }
    return {"status": "passed", "message": "Teste concluído."}


def packaged_grader_main() -> int:
    """Private PyInstaller child entry point; communicates only over stdio pipes."""

    chunks: list[bytes] = []
    size = 0
    while size <= 250_000:
        chunk = os.read(0, min(65_536, 250_001 - size))
        if not chunk:
            break
        chunks.append(chunk)
        size += len(chunk)
    try:
        if size > 250_000:
            raise ValueError("payload too large")
        payload = json.loads(b"".join(chunks))
        if not isinstance(payload, dict):
            raise ValueError("payload must be an object")
        source, test = payload.get("source"), payload.get("test")
        if not isinstance(source, str) or not isinstance(test, str):
            raise ValueError("source and test must be strings")
        policy = OopGradingPolicy()
        violations = policy.violations(source) + policy.violations(
            test, trusted_test=True
        )
        if violations:
            result = {
                "status": "error",
                "message": "Política de segurança: " + "; ".join(violations),
            }
        else:
            result = _evaluate_payload({"source": source, "test": test})
    except (json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
        result = {"status": "error", "message": f"Payload inválido: {exc}"[:1_000]}
    encoded = json.dumps(result, ensure_ascii=True).encode("ascii")
    os.write(1, encoded[:16_384])
    return 0


class IsolatedGradingExecutor:
    def run_test(self, source: str, test_code: str, *, timeout_ms: int) -> tuple[str, str]:
        payload = json.dumps(
            {"source": source, "test": test_code}, ensure_ascii=False
        ).encode("utf-8")
        environment = {"PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8"}
        for inherited_name in ("SYSTEMROOT", "TEMP", "TMP"):
            inherited_value = os.environ.get(inherited_name)
            if inherited_value:
                environment[inherited_name] = inherited_value
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0
            )
        try:
            command = (
                [sys.executable, "--aprendix-grader"]
                if getattr(sys, "frozen", False)
                else [sys.executable, "-I", "-S", "-c", _GRADER_RUNNER]
            )
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                env=environment, creationflags=flags,
            )
            windows_job = WindowsJobLimit.attach(
                process, memory_limit_mb=192, cpu_limit_ms=timeout_ms
            )
            try:
                stdout, _stderr = process.communicate(
                    payload, timeout=timeout_ms / 1000
                )
            finally:
                if windows_job is not None:
                    windows_job.close()
        except subprocess.TimeoutExpired:
            return "timeout", "O teste excedeu o limite de tempo."
        if process.returncode != 0 or len(stdout) > 16_384:
            return "error", "O processo de correção terminou de forma inesperada."
        try:
            result = json.loads(stdout)
            status = result.get("status")
            message = result.get("message")
            if status not in {"passed", "failed", "error"} or not isinstance(message, str):
                raise ValueError
            return status, message[:1_000]
        except (json.JSONDecodeError, ValueError):
            return "error", "A resposta do processo de correção era inválida."
