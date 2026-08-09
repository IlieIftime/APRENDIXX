"""Fail-closed Python policy validation and limited subprocess execution."""

from __future__ import annotations

import ast
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from aprendix.application.contracts import (
    PolicyViolationDTO,
    SandboxRequest,
    SandboxResult,
)
from aprendix.infrastructure.windows_job import WindowsJobLimit

_MAX_AST_NODES: Final = 5_000
_MAX_NESTING: Final = 80
_BANNED_NODE_TYPES: Final = (
    ast.AsyncFunctionDef,
    ast.Await,
    ast.Global,
    ast.Import,
    ast.ImportFrom,
    ast.Nonlocal,
)
_BANNED_CALLS: Final = {
    "__import__",
    "breakpoint",
    "compile",
    "delattr",
    "dir",
    "eval",
    "exec",
    "getattr",
    "globals",
    "help",
    "locals",
    "memoryview",
    "open",
    "setattr",
    "type",
    "vars",
}
_BANNED_ATTRIBUTES: Final = {
    "ag_frame",
    "cr_frame",
    "f_back",
    "f_builtins",
    "f_code",
    "f_globals",
    "f_locals",
    "gi_code",
    "gi_frame",
    "mro",
    "tb_frame",
}


class SandboxInfrastructureError(RuntimeError):
    """Raised internally when a child result cannot be trusted."""


@dataclass(frozen=True, slots=True)
class PythonAstPolicy:
    """Conservative syntax policy for introductory Python exercises."""

    max_ast_nodes: int = _MAX_AST_NODES
    max_nesting: int = _MAX_NESTING
    allow_classes: bool = False

    def validate(self, source_code: str) -> tuple[PolicyViolationDTO, ...]:
        try:
            tree = ast.parse(source_code, mode="exec")
        except SyntaxError as exc:
            return (
                PolicyViolationDTO(
                    rule="syntax.invalid",
                    message=exc.msg,
                    line=max(exc.lineno or 1, 1),
                    column=max((exc.offset or 1) - 1, 0),
                ),
            )

        nodes = list(ast.walk(tree))
        if len(nodes) > self.max_ast_nodes:
            return (
                PolicyViolationDTO(
                    rule="complexity.ast_nodes",
                    message=(
                        f"source contains {len(nodes)} AST nodes; "
                        f"the limit is {self.max_ast_nodes}"
                    ),
                    line=1,
                    column=0,
                ),
            )

        violations: list[PolicyViolationDTO] = []

        def reject(node: ast.AST, rule: str, message: str) -> None:
            if len(violations) >= 100:
                return
            violations.append(
                PolicyViolationDTO(
                    rule=rule,
                    message=message,
                    line=max(getattr(node, "lineno", 1), 1),
                    column=max(getattr(node, "col_offset", 0), 0),
                )
            )

        for node in nodes:
            if isinstance(node, _BANNED_NODE_TYPES) or (
                isinstance(node, ast.ClassDef) and not self.allow_classes
            ):
                reject(
                    node,
                    "syntax.blocked",
                    f"{type(node).__name__} is not allowed in the sandbox",
                )
            elif isinstance(node, ast.ClassDef):
                if node.decorator_list or node.keywords:
                    reject(
                        node,
                        "class.configuration",
                        "class decorators and metaclass options are not allowed",
                    )
                for base in node.bases:
                    if not (isinstance(base, ast.Name) and base.id == "object"):
                        reject(
                            base,
                            "class.inheritance",
                            "only implicit object inheritance is allowed",
                        )
            elif isinstance(node, ast.Name):
                if node.id.startswith("__"):
                    reject(
                        node,
                        "name.dunder",
                        "double-underscore names are not allowed",
                    )
                elif node.id in _BANNED_CALLS:
                    reject(
                        node,
                        "name.blocked",
                        f"{node.id} is not available in the sandbox",
                    )
            elif isinstance(node, ast.Attribute):
                safe_class_dunders = {
                    "__init__", "__str__", "__repr__", "__len__", "__eq__"
                }
                if (
                    (node.attr.startswith("_") and node.attr not in safe_class_dunders)
                    or node.attr in _BANNED_ATTRIBUTES
                ):
                    reject(
                        node,
                        "attribute.blocked",
                        f"attribute {node.attr!r} is not allowed",
                    )
            elif isinstance(node, ast.Constant):
                if (
                    isinstance(node.value, (str, bytes))
                    and len(node.value) > 65_536
                ):
                    reject(
                        node,
                        "literal.too_large",
                        "string and bytes literals are limited to 65536 characters",
                    )

        def depth(node: ast.AST, current: int) -> int:
            if current > self.max_nesting:
                return current
            children = tuple(ast.iter_child_nodes(node))
            if not children:
                return current
            return max(depth(child, current + 1) for child in children)

        if depth(tree, 0) > self.max_nesting:
            reject(
                tree,
                "complexity.nesting",
                f"AST nesting exceeds {self.max_nesting}",
            )

        unique = {
            (item.rule, item.line, item.column, item.message): item
            for item in violations
        }
        return tuple(
            sorted(
                unique.values(),
                key=lambda item: (item.line, item.column, item.rule),
            )
        )


_CHILD_RUNNER: Final = r'''
import json
import math
import sys
import time

payload = json.loads(sys.stdin.buffer.read())
memory_enforced = False
try:
    import resource
    memory_bytes = int(payload["memory_limit_mb"]) * 1024 * 1024
    cpu_seconds = max(1, int(math.ceil(payload["timeout_ms"] / 1000)))
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
    if hasattr(resource, "RLIMIT_NOFILE"):
        resource.setrlimit(resource.RLIMIT_NOFILE, (16, 16))
    memory_enforced = True
except (ImportError, OSError, ValueError):
    memory_enforced = False

limit = int(payload["max_output_bytes"])
output = bytearray()
truncated = False
inputs = iter(payload["stdin"])

def limited_print(*objects, sep=" ", end="\n", flush=False):
    global truncated
    if not isinstance(sep, str) or not isinstance(end, str):
        raise TypeError("sep and end must be strings")
    rendered = (sep.join(str(item) for item in objects) + end).encode(
        "utf-8", errors="replace"
    )
    remaining = max(0, limit - len(output))
    if len(rendered) > remaining:
        output.extend(rendered[:remaining])
        truncated = True
    else:
        output.extend(rendered)

def limited_input(prompt=""):
    if prompt:
        limited_print(prompt, end="")
    try:
        return next(inputs)
    except StopIteration as exc:
        raise EOFError("sandbox input exhausted") from exc

safe_builtins = {
    "__build_class__": __build_class__,
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "Exception": Exception,
    "filter": filter,
    "float": float,
    "frozenset": frozenset,
    "input": limited_input,
    "int": int,
    "isinstance": isinstance,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "object": object,
    "pow": pow,
    "print": limited_print,
    "range": range,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "super": super,
    "sum": sum,
    "tuple": tuple,
    "ValueError": ValueError,
    "zip": zip,
}
namespace = {"__builtins__": safe_builtins, "__name__": "sandbox"}
status = "ok"
error_type = None
error_message = None
execution_started = time.monotonic()
execution_deadline = execution_started + int(payload["timeout_ms"]) / 1000

def execution_trace(frame, event, arg):
    if time.monotonic() > execution_deadline:
        raise TimeoutError("execution time limit exceeded")
    return execution_trace

try:
    compiled = compile(
        payload["source_code"],
        "<aprendix-sandbox>",
        "exec",
        dont_inherit=True,
        optimize=0,
    )
    sys.settrace(execution_trace)
    exec(compiled, namespace, namespace)
    sys.settrace(None)
    if truncated:
        status = "output_limit"
except TimeoutError:
    status = "timeout"
    error_type = "TimeoutExpired"
    error_message = "execution time limit exceeded"
except MemoryError as exc:
    status = "resource_limit"
    error_type = "MemoryError"
    error_message = "memory limit exceeded"
except BaseException as exc:
    status = "runtime_error"
    error_type = type(exc).__name__[:200]
    error_message = str(exc)[:2000]
finally:
    sys.settrace(None)

result = {
    "status": status,
    "stdout": output.decode("utf-8", errors="replace"),
    "error_type": error_type,
    "error_message": error_message,
    "memory_limit_enforced": memory_enforced,
    "output_truncated": truncated,
}
sys.__stdout__.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
sys.__stdout__.flush()
'''


class PythonSandbox:
    """Execute policy-approved Python only in an isolated child interpreter.

    The AST policy narrows the language but is not treated as an OS security
    boundary. The host process never compiles, evaluates, or executes submitted
    source code.
    """

    def __init__(self, policy: PythonAstPolicy | None = None) -> None:
        self._policy = policy or PythonAstPolicy()

    def run(self, request: SandboxRequest) -> SandboxResult:
        started = time.monotonic()
        violations = self._policy.validate(request.source_code)
        if violations:
            return SandboxResult(
                status="rejected",
                duration_ms=self._elapsed_ms(started),
                policy_violations=violations,
                memory_limit_enforced=False,
                error_type="PolicyViolation",
                error_message="source rejected before execution",
            )

        child_payload = json.dumps(
            {
                "source_code": request.source_code,
                "stdin": request.stdin,
                "timeout_ms": request.timeout_ms,
                "max_output_bytes": request.max_output_bytes,
                "memory_limit_mb": request.memory_limit_mb,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        helper_directory = Path(sys.executable).with_name("AprendixSandbox") / "AprendixSandbox.exe"
        helper_file = Path(sys.executable).with_name("AprendixSandbox.exe")
        helper = helper_directory if helper_directory.is_file() else helper_file
        if getattr(sys, "frozen", False):
            command = [str(helper)] if helper.is_file() else [sys.executable, "--aprendix-sandbox"]
        else:
            command = [sys.executable, "-I", "-S", "-c", _CHILD_RUNNER]
        environment = {
            "PYTHONHASHSEED": "0",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
        if os.name == "nt" and "SYSTEMROOT" in os.environ:
            environment["SYSTEMROOT"] = os.environ["SYSTEMROOT"]

        creation_flags = 0
        if os.name == "nt":
            creation_flags = (
                getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            )

        try:
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=environment,
                creationflags=creation_flags,
                start_new_session=os.name != "nt",
            )
        except OSError as exc:
            return SandboxResult(
                status="infrastructure_error",
                duration_ms=self._elapsed_ms(started),
                memory_limit_enforced=False,
                error_type=type(exc).__name__,
                error_message="isolated interpreter could not be started",
            )

        windows_job = WindowsJobLimit.attach(
            process,
            memory_limit_mb=request.memory_limit_mb,
            cpu_limit_ms=request.timeout_ms,
        )
        host_memory_enforced = os.name == "posix" or windows_job is not None

        try:
            startup_allowance_ms = (
                6_000 if getattr(sys, "frozen", False) and helper.is_file()
                else 30_000 if getattr(sys, "frozen", False)
                else 0
            )
            stdout, stderr = process.communicate(
                child_payload,
                timeout=(request.timeout_ms + startup_allowance_ms) / 1_000,
            )
        except subprocess.TimeoutExpired:
            self._terminate(process)
            process.communicate()
            if windows_job is not None:
                windows_job.close()
            return SandboxResult(
                status="timeout",
                duration_ms=self._elapsed_ms(started),
                exit_code=process.returncode,
                memory_limit_enforced=host_memory_enforced,
                error_type="TimeoutExpired",
                error_message=f"execution exceeded {request.timeout_ms} ms",
            )

        if windows_job is not None:
            windows_job.close()

        maximum_envelope = request.max_output_bytes * 6 + 16_384
        if len(stdout) > maximum_envelope:
            return SandboxResult(
                status="infrastructure_error",
                duration_ms=self._elapsed_ms(started),
                exit_code=process.returncode,
                memory_limit_enforced=host_memory_enforced,
                error_type="MalformedChildOutput",
                error_message="child result exceeded the trusted envelope size",
            )
        if process.returncode != 0:
            message = stderr.decode("utf-8", errors="replace")[:500]
            return SandboxResult(
                status="resource_limit",
                duration_ms=self._elapsed_ms(started),
                exit_code=process.returncode,
                memory_limit_enforced=host_memory_enforced,
                error_type="ChildTerminated",
                error_message=message or "child terminated without a trusted result",
            )
        try:
            decoded = json.loads(stdout.decode("utf-8", errors="replace"))
            if not isinstance(decoded, dict):
                raise SandboxInfrastructureError("child response is not an object")
            status = decoded.get("status")
            if status not in {
                "ok",
                "runtime_error",
                "output_limit",
                "resource_limit",
                "timeout",
            }:
                raise SandboxInfrastructureError("child returned an unknown status")
            child_stdout = decoded.get("stdout")
            if not isinstance(child_stdout, str):
                raise SandboxInfrastructureError("child stdout is not text")
            if len(child_stdout.encode("utf-8")) > request.max_output_bytes + 3:
                raise SandboxInfrastructureError("child bypassed its output limit")
            return SandboxResult(
                status=status,
                stdout=child_stdout,
                duration_ms=self._elapsed_ms(started),
                exit_code=process.returncode,
                error_type=decoded.get("error_type"),
                error_message=decoded.get("error_message"),
                memory_limit_enforced=(
                    host_memory_enforced
                    or bool(decoded.get("memory_limit_enforced"))
                ),
                output_truncated=bool(decoded.get("output_truncated")),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, SandboxInfrastructureError) as exc:
            return SandboxResult(
                status="infrastructure_error",
                duration_ms=self._elapsed_ms(started),
                exit_code=process.returncode,
                memory_limit_enforced=host_memory_enforced,
                error_type=type(exc).__name__,
                error_message="child returned an invalid result envelope",
            )

    @staticmethod
    def _elapsed_ms(started: float) -> int:
        return max(0, int((time.monotonic() - started) * 1_000))

    @staticmethod
    def _terminate(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
                return
            except ProcessLookupError:
                return
        process.kill()


def packaged_sandbox_main() -> int:
    """Private child entry point used by a frozen one-file executable."""

    import io

    # A PyInstaller ``console=False`` application initializes the Python stdio
    # objects as None even when the parent process supplied OS-level pipes.
    # Bind only duplicated pipe descriptors; no console or filesystem is opened.
    binary_input = os.fdopen(os.dup(0), "rb", closefd=True)
    binary_output = os.fdopen(os.dup(1), "wb", closefd=True)
    sys.stdin = io.TextIOWrapper(binary_input, encoding="utf-8")
    sys.__stdout__ = io.TextIOWrapper(binary_output, encoding="utf-8")
    namespace: dict[str, object] = {"__name__": "__aprendix_sandbox_child__"}
    exec(compile(_CHILD_RUNNER, "<aprendix-sandbox-runner>", "exec"), namespace, namespace)
    sys.__stdout__.flush()
    return 0
