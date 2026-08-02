"""A small budgeted Python interpreter for untrusted mobile exercises.

This module intentionally never compiles or executes learner source.  It walks
an allow-listed AST and represents functions, classes and instances with local
objects which expose no host Python internals.
"""

from __future__ import annotations

import ast
import operator
import time
from dataclasses import dataclass
from typing import Any, Callable


class ExecutionLimitError(RuntimeError):
    pass


class UnsupportedSyntaxError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ExecutionLimits:
    timeout_ms: int = 1_500
    max_steps: int = 50_000
    max_output_bytes: int = 16_384
    max_collection_items: int = 4_096
    max_string_chars: int = 65_536
    max_integer_bits: int = 4_096
    max_call_depth: int = 40
    max_ast_nodes: int = 5_000


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    status: str
    stdout: str = ""
    steps: int = 0
    duration_ms: int = 0
    error_type: str | None = None
    error_message: str | None = None


class _Return(Exception):
    def __init__(self, value: Any) -> None:
        self.value = value


class _Break(Exception):
    pass


class _Continue(Exception):
    pass


class _Environment:
    def __init__(self, parent: "_Environment | None" = None) -> None:
        self.values: dict[str, Any] = {}
        self.parent = parent

    def get(self, name: str) -> Any:
        if name in self.values:
            return self.values[name]
        if self.parent is not None:
            return self.parent.get(name)
        raise NameError(f"name {name!r} is not defined")

    def set(self, name: str, value: Any) -> None:
        self.values[name] = value


@dataclass(slots=True)
class _SafeFunction:
    interpreter: "RestrictedPython"
    node: ast.FunctionDef
    closure: _Environment

    def invoke(self, args: list[Any], depth: int, bound_self: "_SafeInstance | None" = None) -> Any:
        parameters = [item.arg for item in self.node.args.args]
        values = ([bound_self] if bound_self is not None else []) + args
        if self.node.args.vararg or self.node.args.kwarg or self.node.args.kwonlyargs:
            raise UnsupportedSyntaxError("variadic and keyword-only parameters are not supported")
        required = len(parameters) - len(self.node.args.defaults)
        if not required <= len(values) <= len(parameters):
            raise TypeError(f"{self.node.name} expects {required}..{len(parameters)} arguments")
        frame = _Environment(self.closure)
        for name, value in zip(parameters, values, strict=False):
            frame.set(name, value)
        missing = len(parameters) - len(values)
        if missing:
            defaults = self.node.args.defaults[-missing:]
            for name, default in zip(parameters[-missing:], defaults, strict=True):
                frame.set(name, self.interpreter._eval(default, self.closure, depth + 1))
        try:
            self.interpreter._block(self.node.body, frame, depth + 1)
        except _Return as signal:
            return signal.value
        return None


@dataclass(slots=True)
class _SafeClass:
    name: str
    methods: dict[str, _SafeFunction]


@dataclass(slots=True)
class _SafeInstance:
    class_value: _SafeClass
    attributes: dict[str, Any]


@dataclass(slots=True)
class _BoundMethod:
    function: _SafeFunction
    instance: _SafeInstance


@dataclass(slots=True)
class _CollectionMethod:
    owner: Any
    name: str


class RestrictedPython:
    """Execute a useful teaching subset of Python with deterministic budgets."""

    _binary: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
        ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
        ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod, ast.Pow: operator.pow,
    }
    _compare: dict[type[ast.cmpop], Callable[[Any, Any], bool]] = {
        ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
        ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge,
        ast.In: lambda a, b: a in b, ast.NotIn: lambda a, b: a not in b,
        ast.Is: operator.is_, ast.IsNot: operator.is_not,
    }

    def __init__(self, limits: ExecutionLimits | None = None) -> None:
        self.limits = limits or ExecutionLimits()
        self._steps = 0
        self._deadline = 0.0
        self._output: list[str] = []
        self._output_bytes = 0
        self._builtins: dict[str, Callable[..., Any]] = {
            "abs": abs, "all": all, "any": any, "bool": bool,
            "dict": dict, "enumerate": lambda value: list(enumerate(value)),
            "float": float, "int": int, "len": len, "list": list,
            "max": max, "min": min, "range": self._safe_range,
            "reversed": lambda value: list(reversed(value)), "round": round,
            "set": set, "sorted": sorted, "str": str, "sum": sum,
            "tuple": tuple, "zip": lambda *values: list(zip(*values)),
            "print": self._print,
        }

    def run(self, source: str) -> ExecutionResult:
        started = time.monotonic()
        self._steps, self._output, self._output_bytes = 0, [], 0
        self._deadline = started + self.limits.timeout_ms / 1_000
        try:
            tree = ast.parse(source, mode="exec")
            if sum(1 for _ in ast.walk(tree)) > self.limits.max_ast_nodes:
                raise ExecutionLimitError("AST node budget exceeded")
            self._reject_forbidden(tree)
            self._block(tree.body, _Environment(), 0)
            status, error_type, error_message = "ok", None, None
        except SyntaxError as exc:
            status, error_type = "syntax_error", "SyntaxError"
            error_message = f"line {exc.lineno}: {exc.msg}"
        except ExecutionLimitError as exc:
            status, error_type, error_message = "limit", type(exc).__name__, str(exc)
        except UnsupportedSyntaxError as exc:
            status, error_type, error_message = "rejected", type(exc).__name__, str(exc)
        except BaseException as exc:
            status, error_type, error_message = "runtime_error", type(exc).__name__, str(exc)[:1_000]
        return ExecutionResult(
            status=status, stdout="".join(self._output), steps=self._steps,
            duration_ms=max(0, int((time.monotonic() - started) * 1_000)),
            error_type=error_type, error_message=error_message,
        )

    @staticmethod
    def _reject_forbidden(tree: ast.AST) -> None:
        forbidden = (
            ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal, ast.AsyncFunctionDef,
            ast.Await, ast.Lambda, ast.With, ast.Try, ast.Raise, ast.Delete,
            ast.Yield, ast.YieldFrom, ast.Match, ast.NamedExpr,
            ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
        )
        for node in ast.walk(tree):
            if isinstance(node, forbidden):
                raise UnsupportedSyntaxError(f"{type(node).__name__} is not supported")
            if isinstance(node, ast.Name) and node.id.startswith("_"):
                raise UnsupportedSyntaxError("private names are not available")
            if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
                raise UnsupportedSyntaxError("private attributes are not available")
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                if node.name.startswith("_") and node.name != "__init__":
                    raise UnsupportedSyntaxError("private definitions are not available")
                if node.decorator_list:
                    raise UnsupportedSyntaxError("decorators are not supported")
            if isinstance(node, ast.ClassDef) and (node.bases or node.keywords):
                raise UnsupportedSyntaxError("inheritance and metaclasses are not supported")

    def _tick(self, amount: int = 1, depth: int = 0) -> None:
        self._steps += amount
        if self._steps > self.limits.max_steps:
            raise ExecutionLimitError("instruction budget exceeded")
        if depth > self.limits.max_call_depth:
            raise ExecutionLimitError("call depth exceeded")
        if time.monotonic() > self._deadline:
            raise ExecutionLimitError("time budget exceeded")

    def _check_value(self, value: Any) -> Any:
        if isinstance(value, int) and value.bit_length() > self.limits.max_integer_bits:
            raise ExecutionLimitError("integer size budget exceeded")
        if isinstance(value, str) and len(value) > self.limits.max_string_chars:
            raise ExecutionLimitError("string size budget exceeded")
        if isinstance(value, (list, tuple, dict, set)):
            if len(value) > self.limits.max_collection_items:
                raise ExecutionLimitError("collection size budget exceeded")
        return value

    def _print(self, *items: Any, sep: str = " ", end: str = "\n") -> None:
        if not isinstance(sep, str) or not isinstance(end, str):
            raise TypeError("sep and end must be strings")
        text = sep.join(self._display(item) for item in items) + end
        encoded = text.encode("utf-8", errors="replace")
        remaining = self.limits.max_output_bytes - self._output_bytes
        if len(encoded) > remaining:
            if remaining > 0:
                self._output.append(encoded[:remaining].decode("utf-8", errors="ignore"))
                self._output_bytes = self.limits.max_output_bytes
            raise ExecutionLimitError("output budget exceeded")
        self._output.append(text)
        self._output_bytes += len(encoded)

    @staticmethod
    def _display(value: Any) -> str:
        if isinstance(value, _SafeInstance):
            return f"<{value.class_value.name} object>"
        return str(value)

    def _safe_range(self, *args: int) -> list[int]:
        result = range(*args)
        if len(result) > self.limits.max_collection_items:
            raise ExecutionLimitError("range size budget exceeded")
        return list(result)

    def _block(self, statements: list[ast.stmt], env: _Environment, depth: int) -> None:
        for statement in statements:
            self._statement(statement, env, depth)

    def _statement(self, node: ast.stmt, env: _Environment, depth: int) -> None:
        self._tick(depth=depth)
        if isinstance(node, ast.Expr):
            self._eval(node.value, env, depth)
        elif isinstance(node, ast.Assign):
            value = self._eval(node.value, env, depth)
            for target in node.targets:
                self._assign(target, value, env, depth)
        elif isinstance(node, ast.AnnAssign):
            if node.value is not None:
                self._assign(node.target, self._eval(node.value, env, depth), env, depth)
        elif isinstance(node, ast.AugAssign):
            left = self._read_target(node.target, env, depth)
            value = self._apply_binary(node.op, left, self._eval(node.value, env, depth))
            self._assign(node.target, value, env, depth)
        elif isinstance(node, ast.If):
            self._block(node.body if self._eval(node.test, env, depth) else node.orelse, env, depth)
        elif isinstance(node, ast.While):
            while self._eval(node.test, env, depth):
                self._tick(depth=depth)
                try:
                    self._block(node.body, env, depth)
                except _Continue:
                    continue
                except _Break:
                    break
            else:
                self._block(node.orelse, env, depth)
        elif isinstance(node, ast.For):
            iterable = self._eval(node.iter, env, depth)
            broken = False
            for item in iterable:
                self._tick(depth=depth)
                self._assign(node.target, item, env, depth)
                try:
                    self._block(node.body, env, depth)
                except _Continue:
                    continue
                except _Break:
                    broken = True
                    break
            if not broken:
                self._block(node.orelse, env, depth)
        elif isinstance(node, ast.FunctionDef):
            env.set(node.name, _SafeFunction(self, node, env))
        elif isinstance(node, ast.ClassDef):
            methods = {
                item.name: _SafeFunction(self, item, env)
                for item in node.body if isinstance(item, ast.FunctionDef)
            }
            if any(not isinstance(item, (ast.FunctionDef, ast.Pass)) for item in node.body):
                raise UnsupportedSyntaxError("class bodies may only contain methods")
            env.set(node.name, _SafeClass(node.name, methods))
        elif isinstance(node, ast.Return):
            raise _Return(self._eval(node.value, env, depth) if node.value else None)
        elif isinstance(node, ast.Break):
            raise _Break()
        elif isinstance(node, ast.Continue):
            raise _Continue()
        elif isinstance(node, ast.Pass):
            return
        else:
            raise UnsupportedSyntaxError(f"statement {type(node).__name__} is not supported")

    def _eval(self, node: ast.expr, env: _Environment, depth: int) -> Any:
        self._tick(depth=depth)
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (str, int, float, bool, type(None))):
                raise UnsupportedSyntaxError("literal type is not supported")
            return self._check_value(node.value)
        if isinstance(node, ast.Name):
            if node.id in self._builtins:
                return self._builtins[node.id]
            return env.get(node.id)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            values = [self._eval(item, env, depth) for item in node.elts]
            result = list(values) if isinstance(node, ast.List) else tuple(values) if isinstance(node, ast.Tuple) else set(values)
            return self._check_value(result)
        if isinstance(node, ast.Dict):
            return self._check_value({
                self._eval(key, env, depth): self._eval(value, env, depth)
                for key, value in zip(node.keys, node.values, strict=True)
            })
        if isinstance(node, ast.BinOp):
            return self._apply_binary(node.op, self._eval(node.left, env, depth), self._eval(node.right, env, depth))
        if isinstance(node, ast.UnaryOp):
            value = self._eval(node.operand, env, depth)
            result = {-1: None}
            if isinstance(node.op, ast.Not): result = not value
            elif isinstance(node.op, ast.USub): result = -value
            elif isinstance(node.op, ast.UAdd): result = +value
            else: raise UnsupportedSyntaxError("unary operator is not supported")
            return self._check_value(result)
        if isinstance(node, ast.BoolOp):
            values = node.values
            result = self._eval(values[0], env, depth)
            for item in values[1:]:
                if isinstance(node.op, ast.And) and not result: return result
                if isinstance(node.op, ast.Or) and result: return result
                result = self._eval(item, env, depth)
            return result
        if isinstance(node, ast.Compare):
            left = self._eval(node.left, env, depth)
            for operation, comparator in zip(node.ops, node.comparators, strict=True):
                right = self._eval(comparator, env, depth)
                function = self._compare.get(type(operation))
                if function is None or not function(left, right): return False
                left = right
            return True
        if isinstance(node, ast.IfExp):
            return self._eval(node.body if self._eval(node.test, env, depth) else node.orelse, env, depth)
        if isinstance(node, ast.Call):
            if node.keywords:
                if not (isinstance(node.func, ast.Name) and node.func.id == "print"):
                    raise UnsupportedSyntaxError("keyword arguments are only supported by print")
                kwargs = {item.arg: self._eval(item.value, env, depth) for item in node.keywords if item.arg}
            else:
                kwargs = {}
            function = self._eval(node.func, env, depth)
            args = [self._eval(item, env, depth) for item in node.args]
            if isinstance(function, _SafeFunction): return self._check_value(function.invoke(args, depth + 1))
            if isinstance(function, _BoundMethod): return self._check_value(function.function.invoke(args, depth + 1, function.instance))
            if isinstance(function, _SafeClass):
                instance = _SafeInstance(function, {})
                initializer = function.methods.get("__init__")
                if initializer: initializer.invoke(args, depth + 1, instance)
                elif args: raise TypeError(f"{function.name} takes no arguments")
                return instance
            if isinstance(function, _CollectionMethod):
                allowed = {
                    "append", "clear", "copy", "count", "extend", "get",
                    "index", "insert", "items", "keys", "pop", "remove",
                    "reverse", "sort", "update", "values", "add", "discard",
                }
                if function.name not in allowed:
                    raise UnsupportedSyntaxError("collection method is not allowed")
                result = getattr(function.owner, function.name)(*args)
                self._check_value(function.owner)
                return self._check_value(result)
            if function not in self._builtins.values():
                raise UnsupportedSyntaxError("call target is not allowed")
            return self._check_value(function(*args, **kwargs))
        if isinstance(node, ast.Attribute):
            instance = self._eval(node.value, env, depth)
            if isinstance(instance, _SafeInstance):
                if node.attr in instance.attributes: return instance.attributes[node.attr]
                if node.attr in instance.class_value.methods: return _BoundMethod(instance.class_value.methods[node.attr], instance)
                raise AttributeError(node.attr)
            if isinstance(instance, (list, dict, set)):
                return _CollectionMethod(instance, node.attr)
            raise UnsupportedSyntaxError("host object attributes are not available")
        if isinstance(node, ast.Subscript):
            value = self._eval(node.value, env, depth)
            key = self._eval(node.slice, env, depth)
            return value[key]
        if isinstance(node, ast.Slice):
            return slice(
                self._eval(node.lower, env, depth) if node.lower else None,
                self._eval(node.upper, env, depth) if node.upper else None,
                self._eval(node.step, env, depth) if node.step else None,
            )
        raise UnsupportedSyntaxError(f"expression {type(node).__name__} is not supported")

    def _apply_binary(self, operation: ast.operator, left: Any, right: Any) -> Any:
        if isinstance(operation, ast.Pow) and isinstance(right, int) and abs(right) > 1_024:
            raise ExecutionLimitError("exponent budget exceeded")
        function = self._binary.get(type(operation))
        if function is None:
            raise UnsupportedSyntaxError("binary operator is not supported")
        return self._check_value(function(left, right))

    def _read_target(self, target: ast.expr, env: _Environment, depth: int) -> Any:
        return self._eval(target, env, depth)

    def _assign(self, target: ast.expr, value: Any, env: _Environment, depth: int) -> None:
        self._check_value(value)
        if isinstance(target, ast.Name):
            env.set(target.id, value)
        elif isinstance(target, (ast.Tuple, ast.List)):
            values = list(value)
            if len(values) != len(target.elts): raise ValueError("unpack length mismatch")
            for child, child_value in zip(target.elts, values, strict=True): self._assign(child, child_value, env, depth)
        elif isinstance(target, ast.Attribute):
            instance = self._eval(target.value, env, depth)
            if not isinstance(instance, _SafeInstance): raise UnsupportedSyntaxError("attribute assignment is restricted to learner instances")
            instance.attributes[target.attr] = value
            self._check_value(instance.attributes)
        elif isinstance(target, ast.Subscript):
            container = self._eval(target.value, env, depth)
            key = self._eval(target.slice, env, depth)
            container[key] = value
            self._check_value(container)
        else:
            raise UnsupportedSyntaxError("assignment target is not supported")
