"""Authenticated pipe debugger running Python tracing in an isolated process."""

from __future__ import annotations

import ast
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
from aprendix.application.contracts import (
    DebugFrameDTO,
    DebugRequestDTO,
    DebugSessionDTO,
)
from aprendix.infrastructure.sandbox import PythonAstPolicy
from aprendix.infrastructure.windows_job import WindowsJobLimit


_EXPRESSION_NODES = (
    ast.Expression, ast.Name, ast.Load, ast.Constant, ast.Tuple, ast.List,
    ast.Dict, ast.Set, ast.Subscript, ast.Slice, ast.BinOp, ast.BoolOp,
    ast.Compare, ast.UnaryOp, ast.Add, ast.Sub, ast.Mult, ast.Div, ast.FloorDiv,
    ast.Mod, ast.Pow, ast.And, ast.Or, ast.Not, ast.USub, ast.UAdd, ast.Eq,
    ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is,
    ast.IsNot,
)


def _validate_expression(value: str) -> None:
    if not value.strip():
        return
    try:
        tree = ast.parse(value, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"Expressão de debug inválida: {exc.msg}.") from exc
    if len(list(ast.walk(tree))) > 100:
        raise ValueError("Expressão de debug demasiado complexa.")
    for node in ast.walk(tree):
        if not isinstance(node, _EXPRESSION_NODES):
            raise ValueError(f"Construção bloqueada numa expressão de debug: {type(node).__name__}.")
        if isinstance(node, ast.Name) and node.id.startswith("_"):
            raise ValueError("Nomes privados não são permitidos em watches ou condições.")


_CHILD_DEBUGGER = r'''
import ast
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
    pass

limit = int(payload["max_output_bytes"])
max_steps = int(payload["max_steps"])
deadline = time.monotonic() + int(payload["timeout_ms"]) / 1000
output = bytearray()
truncated = False
frames = []
executed = set()
inputs = iter(payload["stdin"])

def limited_print(*objects, sep=" ", end="\n", flush=False):
    global truncated
    rendered = (sep.join(str(item) for item in objects) + end).encode("utf-8", "replace")
    remaining = max(0, limit - len(output))
    output.extend(rendered[:remaining])
    truncated = truncated or len(rendered) > remaining

def limited_input(prompt=""):
    if prompt:
        limited_print(prompt, end="")
    try:
        return next(inputs)
    except StopIteration as exc:
        raise EOFError("sandbox input exhausted") from exc

safe_builtins = {
    "__build_class__": __build_class__, "abs": abs, "all": all, "any": any,
    "bool": bool, "dict": dict, "divmod": divmod, "enumerate": enumerate,
    "Exception": Exception, "filter": filter, "float": float, "frozenset": frozenset,
    "input": limited_input, "int": int, "isinstance": isinstance, "len": len,
    "list": list, "map": map, "max": max, "min": min, "next": next,
    "object": object, "pow": pow, "print": limited_print, "range": range,
    "reversed": reversed, "round": round, "set": set, "slice": slice,
    "sorted": sorted, "str": str, "super": super, "sum": sum, "tuple": tuple,
    "ValueError": ValueError, "zip": zip,
}
namespace = {"__builtins__": safe_builtins, "__name__": "sandbox"}

def safe_value(value, depth=0):
    if value is None or isinstance(value, (bool, int, float)):
        return repr(value)[:500]
    if isinstance(value, str):
        return repr(value[:480])
    if isinstance(value, bytes):
        return f"<bytes {len(value)}>"
    if depth < 1 and isinstance(value, (list, tuple, set, frozenset)):
        values = list(value)[:12]
        return type(value).__name__ + "([" + ", ".join(safe_value(x, 1) for x in values) + (
            ", …])" if len(value) > 12 else "])"
        )
    if depth < 1 and isinstance(value, dict):
        values = list(value.items())[:12]
        return "{" + ", ".join(safe_value(k, 1) + ": " + safe_value(v, 1) for k,v in values) + (
            ", …}" if len(value) > 12 else "}"
        )
    return "<" + type(value).__name__[:100] + ">"

watch_code = {item: compile(item, "<watch>", "eval", dont_inherit=True)
              for item in payload["watches"]}
conditions = {int(item["line"]): compile(item["condition"], "<condition>", "eval", dont_inherit=True)
              for item in payload["breakpoints"] if item["condition"]}
breakpoint_lines = {int(item["line"]) for item in payload["breakpoints"]}

class StepLimit(Exception):
    pass

def trace(frame, event, arg):
    if frame.f_code.co_filename != "<aprendix-debug>":
        return trace
    if time.monotonic() > deadline:
        raise TimeoutError("debug time limit exceeded")
    if event not in {"call", "line", "return", "exception"}:
        return trace
    if len(frames) >= max_steps:
        raise StepLimit("debug step limit exceeded")
    line = max(1, int(frame.f_lineno))
    if event == "line":
        executed.add(line)
    local_values = {str(k)[:100]: safe_value(v) for k,v in list(frame.f_locals.items())[:30]
                    if not str(k).startswith("__")}
    global_values = {str(k)[:100]: safe_value(v) for k,v in list(frame.f_globals.items())[:20]
                     if not str(k).startswith("__") and k != "__builtins__"}
    merged = dict(frame.f_globals); merged.update(frame.f_locals)
    watch_values = {}
    for expression, code in watch_code.items():
        try:
            watch_values[expression] = safe_value(eval(code, {"__builtins__": {}}, merged))
        except BaseException as exc:
            watch_values[expression] = "<" + type(exc).__name__ + ">"
    breakpoint_hit = line in breakpoint_lines
    if breakpoint_hit and line in conditions:
        try:
            breakpoint_hit = bool(eval(conditions[line], {"__builtins__": {}}, merged))
        except BaseException:
            breakpoint_hit = False
    depth = 0; parent = frame.f_back
    while parent is not None and depth < 200:
        depth += 1; parent = parent.f_back
    frames.append({
        "step": len(frames) + 1, "line": line, "event": event,
        "function": frame.f_code.co_name[:200], "call_depth": depth,
        "locals": local_values, "globals": global_values, "watches": watch_values,
        "stdout": output.decode("utf-8", "replace"), "breakpoint_hit": breakpoint_hit,
    })
    return trace

status = "completed"; error_type = None; error_message = None
started = time.monotonic()
try:
    code = compile(payload["source_code"], "<aprendix-debug>", "exec", dont_inherit=True, optimize=0)
    sys.settrace(trace)
    exec(code, namespace, namespace)
    if truncated:
        status = "output_limit"
except StepLimit as exc:
    status = "step_limit"; error_type = "StepLimit"; error_message = str(exc)
except TimeoutError as exc:
    status = "timeout"; error_type = "TimeoutExpired"; error_message = str(exc)
except MemoryError:
    status = "runtime_error"; error_type = "MemoryError"; error_message = "memory limit exceeded"
except BaseException as exc:
    status = "runtime_error"; error_type = type(exc).__name__[:200]; error_message = str(exc)[:2000]
finally:
    sys.settrace(None)

result = {
    "token": payload["token"], "status": status, "frames": frames,
    "stdout": output.decode("utf-8", "replace"),
    "duration_ms": max(0, round((time.monotonic()-started)*1000)),
    "executed_lines": sorted(executed), "error_type": error_type,
    "error_message": error_message, "memory_limit_enforced": memory_enforced,
}
sys.__stdout__.write(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
sys.__stdout__.flush()
'''


class IsolatedPythonDebugger:
    def __init__(self, policy: PythonAstPolicy | None = None) -> None:
        self._policy = policy or PythonAstPolicy(allow_classes=True)

    def debug(self, request: DebugRequestDTO) -> DebugSessionDTO:
        started = time.monotonic()
        violations = self._policy.validate(request.source_code)
        if violations:
            return DebugSessionDTO(
                status="rejected", duration_ms=round((time.monotonic()-started)*1000),
                error_type="PolicyViolation",
                error_message="; ".join(item.message for item in violations[:5]),
            )
        for watch in request.watches:
            _validate_expression(watch)
        for breakpoint in request.breakpoints:
            _validate_expression(breakpoint.condition)
        executable_lines = {
            int(node.lineno) for node in ast.walk(ast.parse(request.source_code))
            if hasattr(node, "lineno")
        }
        token = secrets.token_hex(32)
        payload = request.model_dump(mode="json")
        payload["token"] = token
        command = (
            [sys.executable, "--aprendix-debugger"] if getattr(sys, "frozen", False)
            else [sys.executable, "-I", "-S", "-c", _CHILD_DEBUGGER]
        )
        environment = {"PYTHONHASHSEED": "0", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        startup = None
        if os.name == "nt":
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = subprocess.SW_HIDE
        windows_job: WindowsJobLimit | None = None
        try:
            with tempfile.TemporaryDirectory(prefix="aprendix-debug-") as directory:
                process = subprocess.Popen(
                    command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, cwd=directory, env=environment,
                    startupinfo=startup,
                )
                windows_job = WindowsJobLimit.attach(
                    process,
                    memory_limit_mb=request.memory_limit_mb,
                    cpu_limit_ms=request.timeout_ms,
                )
                stdout, stderr = process.communicate(
                    json.dumps(payload, ensure_ascii=False).encode(),
                    timeout=request.timeout_ms / 1000 + 1.5,
                )
        except subprocess.TimeoutExpired:
            process.kill(); process.communicate()
            if windows_job is not None:
                windows_job.close()
            return DebugSessionDTO(
                status="timeout", duration_ms=round((time.monotonic()-started)*1000),
                error_type="TimeoutExpired", error_message="debugger helper timed out",
            )
        except (OSError, ValueError) as exc:
            if windows_job is not None:
                windows_job.close()
            return DebugSessionDTO(
                status="infrastructure_error",
                duration_ms=round((time.monotonic()-started)*1000),
                error_type=type(exc).__name__, error_message=str(exc)[:2000],
            )
        host_memory_enforced = os.name == "posix" or windows_job is not None
        if windows_job is not None:
            windows_job.close()
        try:
            result = json.loads(stdout.decode("utf-8"))
            if not secrets.compare_digest(str(result.pop("token", "")), token):
                raise ValueError("debugger IPC challenge mismatch")
            frame_payload = result.pop("frames", ())
            executed = tuple(int(item) for item in result.get("executed_lines", ()))
            coverage = 100.0 * len(set(executed) & executable_lines) / max(1, len(executable_lines))
            result["memory_limit_enforced"] = (
                host_memory_enforced
                or bool(result.get("memory_limit_enforced"))
            )
            return DebugSessionDTO(
                **result, frames=tuple(DebugFrameDTO(**item) for item in frame_payload),
                coverage_percent=min(100.0, coverage), token_verified=True,
            )
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            message = stderr.decode("utf-8", "replace")[:1500] or str(exc)
            return DebugSessionDTO(
                status="infrastructure_error",
                duration_ms=round((time.monotonic()-started)*1000),
                error_type=type(exc).__name__, error_message=message,
                memory_limit_enforced=host_memory_enforced,
            )


def packaged_debugger_main() -> int:
    exec(compile(_CHILD_DEBUGGER, "<aprendix-debug-helper>", "exec"), {})
    return 0
