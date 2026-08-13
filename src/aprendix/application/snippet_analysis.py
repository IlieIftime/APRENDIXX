"""Bounded, explainable static analysis for Python and pseudocode.

This module never imports or executes user input.  Optional runtime tracing is a
different application action and must go through the existing sandbox.
"""

from __future__ import annotations

import ast
import builtins
import re
import time
from collections import Counter
from dataclasses import dataclass, field, is_dataclass
from dataclasses import fields as dataclass_fields
from typing import Any

from aprendix.application.editor_support import diagnose_python
from aprendix.application.text_normalization import (
    TextNormalizationService,
    TextProfile,
)


@dataclass(frozen=True, slots=True)
class AnalysisBudget:
    max_bytes: int = 100_000
    max_nodes: int = 12_000
    max_depth: int = 80
    max_ms: float = 1_500.0
    max_diagnostics: int = 500

    def __post_init__(self) -> None:
        if not 1_000 <= self.max_bytes <= 1_000_000:
            raise ValueError("max_bytes must be between 1,000 and 1,000,000")
        if not 100 <= self.max_nodes <= 100_000:
            raise ValueError("max_nodes must be between 100 and 100,000")
        if not 10 <= self.max_depth <= 500:
            raise ValueError("max_depth must be between 10 and 500")
        if not 25 <= self.max_ms <= 60_000:
            raise ValueError("max_ms must be between 25 and 60,000")


@dataclass(slots=True)
class _Definition:
    name: str
    kind: str
    node: ast.AST
    inferred_type: str | None = None


@dataclass(slots=True)
class _Use:
    name: str
    node: ast.Name
    scope: _Scope


@dataclass(slots=True)
class _Scope:
    name: str
    parent: _Scope | None
    definitions: dict[str, _Definition] = field(default_factory=dict)
    uses: Counter[str] = field(default_factory=Counter)
    global_names: set[str] = field(default_factory=set)
    nonlocal_names: set[str] = field(default_factory=set)

    def resolve(self, name: str) -> _Definition | None:
        current: _Scope | None = self
        while current is not None:
            if name in current.definitions:
                return current.definitions[name]
            current = current.parent
        return None


class _SymbolCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.root = _Scope("module", None)
        self.scope = self.root
        self.scopes = [self.root]
        self.uses: list[_Use] = []
        self._class_stack: list[str] = []

    def _define(
        self, name: str, kind: str, node: ast.AST, inferred_type: str | None = None
    ) -> None:
        target_scope = self.scope
        if name in self.scope.global_names:
            target_scope = self.root
        elif name in self.scope.nonlocal_names:
            current = self.scope.parent
            while current is not None and current.parent is not None:
                if name in current.definitions:
                    target_scope = current
                    break
                current = current.parent
        existing = target_scope.definitions.get(name)
        if existing is None:
            target_scope.definitions[name] = _Definition(name, kind, node, inferred_type)
        elif inferred_type and not existing.inferred_type:
            existing.inferred_type = inferred_type

    def _push(self, name: str) -> None:
        scope = _Scope(f"{self.scope.name}.{name}", self.scope)
        self.scopes.append(scope)
        self.scope = scope

    def _pop(self) -> None:
        assert self.scope.parent is not None
        self.scope = self.scope.parent

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, (ast.Store, ast.Del)):
            self._define(node.id, "variable", node)
        elif isinstance(node.ctx, ast.Load):
            self.scope.uses[node.id] += 1
            self.uses.append(_Use(node.id, node, self.scope))

    def visit_Global(self, node: ast.Global) -> None:
        self.scope.global_names.update(node.names)

    def visit_Nonlocal(self, node: ast.Nonlocal) -> None:
        self.scope.nonlocal_names.update(node.names)

    def visit_Assign(self, node: ast.Assign) -> None:
        inferred = _infer_expression_type(node.value)
        for target in node.targets:
            for name in _target_names(target):
                self._define(name, "variable", target, inferred)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        annotation = _safe_unparse(node.annotation)
        for name in _target_names(node.target):
            self._define(name, "variable", node.target, annotation or None)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        inferred = _infer_expression_type(node.value)
        for name in _target_names(node.target):
            self._define(name, "variable", node.target, inferred)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self._define(alias.asname or alias.name.split(".")[0], "import", node, "module")

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        for alias in node.names:
            if alias.name != "*":
                self._define(alias.asname or alias.name, "import", node, "imported symbol")

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._define(node.name, "function", node, "callable")
        for expression in (*node.decorator_list, *node.args.defaults):
            self.visit(expression)
        for expression in node.args.kw_defaults:
            if expression is not None:
                self.visit(expression)
        self._push(f"{node.name}@{node.lineno}")
        arguments = (
            *node.args.posonlyargs, *node.args.args,
            *((node.args.vararg,) if node.args.vararg else ()),
            *node.args.kwonlyargs,
            *((node.args.kwarg,) if node.args.kwarg else ()),
        )
        for argument in arguments:
            annotation = _safe_unparse(argument.annotation) if argument.annotation else None
            self._define(argument.arg, "parameter", argument, annotation)
        for statement in node.body:
            self.visit(statement)
        self._pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._define(node.name, "class", node, "type")
        for expression in (*node.bases, *node.decorator_list):
            self.visit(expression)
        self._push(f"{node.name}@{node.lineno}")
        self._class_stack.append(node.name)
        for statement in node.body:
            self.visit(statement)
        self._class_stack.pop()
        self._pop()

    def visit_Lambda(self, node: ast.Lambda) -> None:
        self._push(f"lambda@{node.lineno}")
        for argument in (*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs):
            self._define(argument.arg, "parameter", argument)
        self.visit(node.body)
        self._pop()

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node, (node.elt,))

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node, (node.elt,))

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node, (node.elt,))

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node, (node.key, node.value))

    def _visit_comprehension(self, node, outputs: tuple[ast.AST, ...]) -> None:
        if node.generators:
            self.visit(node.generators[0].iter)
        self._push(f"comprehension@{node.lineno}")
        for index, generator in enumerate(node.generators):
            if index:
                self.visit(generator.iter)
            for name in _target_names(generator.target):
                self._define(name, "comprehension variable", generator.target)
            for condition in generator.ifs:
                self.visit(condition)
        for output in outputs:
            self.visit(output)
        self._pop()

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type:
            self.visit(node.type)
        if node.name:
            self._define(node.name, "exception", node, "BaseException")
        for statement in node.body:
            self.visit(statement)


class _CFGBuilder:
    def __init__(self, scope: str) -> None:
        self.scope = scope
        self.blocks: dict[str, dict[str, Any]] = {}
        self._ordinal = 0

    def build(self, statements: list[ast.stmt]) -> tuple[dict[str, Any], ...]:
        self._sequence(statements, (), None, None)
        return tuple(self.blocks.values())

    def _new(self, statement: ast.stmt, successors: tuple[str, ...]) -> str:
        self._ordinal += 1
        identity = f"{self.scope}:L{getattr(statement, 'lineno', 1)}:{self._ordinal}"
        label = _safe_unparse(statement).splitlines()[0][:1_000] or type(statement).__name__
        self.blocks[identity] = {
            "id": identity,
            "scope": self.scope,
            "line": max(1, int(getattr(statement, "lineno", 1))),
            "kind": type(statement).__name__,
            "label": label,
            "successors": successors,
        }
        return identity

    def _sequence(
        self,
        statements: list[ast.stmt],
        follow: tuple[str, ...],
        loop_head: str | None,
        loop_exit: tuple[str, ...] | None,
    ) -> str | None:
        next_ids = follow
        entry: str | None = follow[0] if follow else None
        for statement in reversed(statements):
            if isinstance(statement, (ast.Return, ast.Raise)):
                successors: tuple[str, ...] = ()
            elif isinstance(statement, ast.Break):
                successors = loop_exit or follow
            elif isinstance(statement, ast.Continue):
                successors = (loop_head,) if loop_head else follow
            else:
                successors = next_ids
            identity = self._new(statement, successors)
            if isinstance(statement, ast.If):
                yes = self._sequence(statement.body, next_ids, loop_head, loop_exit)
                no = self._sequence(statement.orelse, next_ids, loop_head, loop_exit)
                choices = tuple(dict.fromkeys(value for value in (yes, no, *next_ids) if value))
                self.blocks[identity]["successors"] = choices[:2]
            elif isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
                body_entry = self._sequence(statement.body, (identity,), identity, next_ids)
                else_entry = self._sequence(statement.orelse, next_ids, loop_head, loop_exit)
                choices = tuple(dict.fromkeys(
                    value for value in (body_entry, else_entry, *next_ids) if value
                ))
                self.blocks[identity]["successors"] = choices[:2]
            elif isinstance(statement, (ast.With, ast.AsyncWith)):
                body_entry = self._sequence(statement.body, next_ids, loop_head, loop_exit)
                self.blocks[identity]["successors"] = (body_entry,) if body_entry else next_ids
            elif isinstance(statement, ast.Try):
                entries = [self._sequence(statement.body, next_ids, loop_head, loop_exit)]
                entries.extend(
                    self._sequence(handler.body, next_ids, loop_head, loop_exit)
                    for handler in statement.handlers
                )
                entries.append(self._sequence(statement.orelse, next_ids, loop_head, loop_exit))
                entries.append(self._sequence(statement.finalbody, next_ids, loop_head, loop_exit))
                self.blocks[identity]["successors"] = tuple(
                    dict.fromkeys(value for value in entries if value)
                )[:20]
            entry, next_ids = identity, (identity,)
        return entry


class SnippetAnalyzer:
    def __init__(self, result_type=None, *, budget: AnalysisBudget | None = None) -> None:
        if result_type is None:
            from aprendix.application.contracts.snippet import SnippetAnalysisDTO
            result_type = SnippetAnalysisDTO
        self._result_type = result_type
        model_fields = getattr(result_type, "model_fields", None)
        if model_fields is not None:
            self._result_fields: frozenset[str] | None = frozenset(model_fields)
        elif is_dataclass(result_type):
            self._result_fields = frozenset(item.name for item in dataclass_fields(result_type))
        else:
            self._result_fields = None
        # Native mobile deliberately ships without Pydantic.  Its compact
        # dataclass result exposes the stable, user-facing analysis fields but
        # not the desktop-only structured diagnostics.  Detect that contract
        # by capability instead of importing either mobile or Pydantic here.
        self._portable_result = (
            self._result_fields is not None and "diagnostics" not in self._result_fields
        )
        self._budget = budget or AnalysisBudget()
        self._normalizer = TextNormalizationService()

    def analyze(self, request, cancellation=None):
        started = time.perf_counter()
        original = request.text
        if len(original.encode("utf-8")) > self._budget.max_bytes:
            raise ValueError("snippet exceeds the static-analysis byte budget")
        normalized = self._normalizer.normalize(original, TextProfile.PYTHON).text.strip()
        language = self._detect(normalized, request.language_hint)
        if self._cancelled(cancellation):
            return self._cancelled_result(request, original, normalized, language, started)
        if language == "python":
            return self._python(request, original, normalized, started, cancellation)
        return self._pseudocode(request, original, normalized, language, started)

    @staticmethod
    def _detect(text: str, hint: str) -> str:
        if hint != "auto":
            return hint
        try:
            tree = ast.parse(text)
            if any(not isinstance(node, (ast.Module, ast.Expr, ast.Constant)) for node in ast.walk(tree)):
                return "python"
        except (SyntaxError, IndentationError):
            if re.search(
                r"(^|\n)\s*(?:def|class|async\s+def|from|import|if|elif|else|for|while|try|except|with)\b|"
                r"\b(?:return|yield|raise|lambda|None|True|False)\b|==|!=|\+=|-=",
                text,
            ):
                return "python"
        if re.search(
            r"\b(SE|ENTAO|SENAO|ENQUANTO|PARA|INICIO|FIM|LER|ESCREVER|ALGORITMO)\b",
            text,
            re.IGNORECASE,
        ):
            return "pseudocode"
        return "text"

    def _python(self, request, original, normalized, started, cancellation):
        if self._portable_result:
            return self._python_portable(
                request, original, normalized, started, cancellation
            )
        from aprendix.application.contracts.snippet import (
            DiagnosticDTO,
            SnippetDiagnosticSeverity,
            SymbolDTO,
        )

        try:
            tree = ast.parse(normalized or "\n", type_comments=True)
        except (SyntaxError, IndentationError) as exc:
            diagnostics = self._syntax_diagnostics(normalized, exc)
            partial = tuple(
                SymbolDTO(name=name, kind=kind, scope="module", line=line, defined=True)
                for name, kind, line in self._partial_symbols(normalized)
            )
            return self._result(
                original=original,
                normalized=normalized,
                detected_language="python",
                summary=(
                    "O trecho parece Python, mas contém sintaxe incompleta. A análise parcial "
                    "não executou o código; corrige primeiro o diagnóstico localizado."
                ),
                complexity_time="indeterminada",
                complexity_space="indeterminada",
                problems=tuple(f"Linha {item.line}: {item.message}" for item in diagnostics),
                suggested_tests=("Depois de corrigir a sintaxe, validar o menor caso permitido.",),
                diagnostics=diagnostics,
                symbols=partial,
                action=request.action,
                action_result=self._action_result(request.action, diagnostics=diagnostics),
                confidence=.58,
                elapsed_ms=self._elapsed(started),
            )

        nodes = tuple(ast.walk(tree))
        depth = self._ast_depth(tree)
        if len(nodes) > self._budget.max_nodes or depth > self._budget.max_depth:
            reason = (
                f"AST excede o orçamento seguro ({len(nodes)} nós, profundidade {depth}; "
                f"máximos {self._budget.max_nodes}/{self._budget.max_depth})."
            )
            diagnostic = DiagnosticDTO(
                code="budget.ast",
                severity=SnippetDiagnosticSeverity.WARNING,
                line=1,
                message=reason,
                evidence="Análise interrompida antes das passagens profundas.",
                confidence=1.0,
            )
            return self._result(
                original=original,
                normalized=normalized,
                detected_language="python",
                summary=f"{reason} O código não foi executado.",
                complexity_time="não calculada",
                complexity_space="não calculada",
                problems=(reason,),
                diagnostics=(diagnostic,),
                action=request.action,
                action_result=reason,
                node_count=len(nodes),
                analysis_truncated=True,
                confidence=.35,
                elapsed_ms=self._elapsed(started),
            )
        if self._cancelled(cancellation):
            return self._cancelled_result(request, original, normalized, "python", started)

        collector = _SymbolCollector()
        collector.visit(tree)
        diagnostics = self._diagnostics(normalized, tree, collector)
        symbols, type_facts = self._symbols(collector)
        functions = self._functions(tree)
        classes = self._classes(tree)
        cfg_blocks = self._cfg(tree)
        call_edges = self._calls(tree)
        complexity = self._complexity(tree)
        security = self._security(tree)
        tests = self._tests(tree, functions)
        imports = self._imports(tree)
        exceptions = self._possible_exceptions(tree)
        constructs = tuple(sorted({type(node).__name__ for node in nodes}))[:100]
        inputs = self._inputs(tree, functions)
        outputs = self._outputs(tree)
        lines = tuple(
            f"Linha {number}: {self._line_meaning(line)}"
            for number, line in enumerate(normalized.splitlines(), 1)
            if line.strip()
        )
        related = self._concepts(constructs)
        proposed = self._proposed_code(request.action.value, normalized, tree)
        action_result = self._action_result(
            request.action,
            diagnostics=diagnostics,
            symbols=symbols,
            functions=functions,
            cfg_blocks=cfg_blocks,
            tests=tests,
            related=related,
        )
        elapsed = self._elapsed(started)
        truncated = elapsed > self._budget.max_ms
        representative_complexity = max(
            complexity,
            key=lambda item: (item.time != "O(1)", item.space != "O(1)", item.cyclomatic),
            default=None,
        )
        if truncated:
            diagnostics = diagnostics + (DiagnosticDTO(
                code="budget.time",
                severity=SnippetDiagnosticSeverity.WARNING,
                line=1,
                message="A análise atingiu o orçamento temporal; o relatório já produzido foi preservado.",
                evidence=f"Tempo decorrido: {elapsed:.1f} ms.",
                confidence=1.0,
            ),)
        legacy_tests = tuple(item.name for item in tests)
        legacy_problems = tuple(f"Linha {item.line}: {item.message}" for item in diagnostics)
        return self._result(
            original=original,
            normalized=normalized,
            detected_language="python",
            summary=(
                f"Análise estática de {len(nodes)} nós: {len(functions)} função(ões), "
                f"{len(classes)} classe(s), {len(symbols)} símbolo(s) e "
                f"{len(diagnostics)} diagnóstico(s). A análise não executou o código."
            ),
            line_explanations=lines,
            inputs=inputs,
            outputs=outputs,
            invariants=self._invariants(tree),
            constructs=constructs,
            control_flow=tuple(
                (block.id, successor) for block in cfg_blocks for successor in block.successors
            )[:5_000],
            complexity_time=representative_complexity.time if representative_complexity else "O(1)",
            complexity_space=representative_complexity.space if representative_complexity else "O(1)",
            problems=legacy_problems[:100],
            suggested_tests=legacy_tests[:100],
            proposed_code=proposed,
            related_concepts=related,
            confidence=.96 if not any(item.severity.value == "error" for item in diagnostics) else .76,
            action=request.action,
            action_result=action_result,
            diagnostics=diagnostics[: self._budget.max_diagnostics],
            symbols=symbols,
            functions=functions,
            classes=classes,
            type_facts=type_facts,
            cfg_blocks=cfg_blocks,
            call_edges=call_edges,
            complexity_findings=complexity,
            security_findings=security,
            test_suggestions=tests,
            imports=imports,
            possible_exceptions=exceptions,
            node_count=len(nodes),
            elapsed_ms=elapsed,
            analysis_truncated=truncated,
        )

    def _python_portable(
        self, request, original, normalized, started, cancellation
    ):
        """Analyse Python for a small stdlib-only result contract.

        Android and iOS use this path so importing or using the analyser does
        not pull the desktop validation stack into the native package.  It is
        intentionally static: user code is parsed but never imported or run.
        """
        try:
            tree = ast.parse(normalized or "\n", type_comments=True)
        except (SyntaxError, IndentationError) as exc:
            line = max(1, int(exc.lineno or 1))
            message = exc.msg or "Sintaxe Python inválida."
            partial = self._partial_symbols(normalized)
            recognized = ", ".join(name for name, _kind, _line in partial[:8])
            detail = f" Símbolos reconhecidos parcialmente: {recognized}." if recognized else ""
            return self._result(
                original=original,
                normalized=normalized,
                detected_language="python",
                summary=(
                    f"A análise estática encontrou sintaxe incompleta na linha {line}: "
                    f"{message}. O código não foi executado.{detail}"
                ),
                complexity_time="indeterminada",
                complexity_space="indeterminada",
                problems=(f"Linha {line}: {message}",),
                suggested_tests=(
                    "Corrigir a sintaxe e validar o menor caso permitido.",
                ),
                confidence=.58,
            )

        nodes = tuple(ast.walk(tree))
        depth = self._ast_depth(tree)
        if len(nodes) > self._budget.max_nodes or depth > self._budget.max_depth:
            reason = (
                f"AST excede o orçamento seguro ({len(nodes)} nós, profundidade {depth}; "
                f"máximos {self._budget.max_nodes}/{self._budget.max_depth})."
            )
            return self._result(
                original=original,
                normalized=normalized,
                detected_language="python",
                summary=f"{reason} O código não foi executado.",
                complexity_time="não calculada",
                complexity_space="não calculada",
                problems=(reason,),
                confidence=.35,
            )
        if self._cancelled(cancellation):
            return self._cancelled_result(
                request, original, normalized, "python", started
            )

        constructs = tuple(sorted({type(node).__name__ for node in nodes}))[:100]
        functions = tuple(
            node for node in nodes
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        loop_depth = max(
            (_max_loop_depth(tree), *(_max_loop_depth(node) for node in functions))
        )
        time_complexity = (
            "O(1)" if loop_depth == 0 else "O(n)" if loop_depth == 1
            else f"O(n^{loop_depth})"
        )
        grows_with_input = any(
            isinstance(node, (
                ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp,
            ))
            for node in nodes
        )
        inputs = [
            f"{node.name}: {argument.arg}"
            for node in functions
            for argument in (
                *node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs,
            )
        ]
        inputs.extend(
            f"Linha {node.lineno}: input()"
            for node in nodes
            if isinstance(node, ast.Call) and _call_name(node.func) == "input"
        )
        outputs = self._outputs(tree)
        lines = tuple(
            f"Linha {number}: {self._line_meaning(line)}"
            for number, line in enumerate(normalized.splitlines(), 1)
            if line.strip()
        )
        related = self._concepts(constructs)
        action = request.action.value
        proposed = self._proposed_code(action, normalized, tree)
        problems = tuple(
            f"Linha {item.line}: {item.message}"
            for item in diagnose_python(normalized)
        )[:100]
        branch_count = sum(
            isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.Match))
            for node in nodes
        )
        suggested_tests = ["Caso nominal com a menor entrada válida"]
        if inputs:
            suggested_tests.extend(("Entrada vazia", "Entrada no limite do contrato"))
        if branch_count:
            suggested_tests.append("Um caso por ramo de decisão")
        if not inputs and not branch_count:
            suggested_tests.append("Confirmar o resultado observável")
        return self._result(
            original=original,
            normalized=normalized,
            detected_language="python",
            summary=(
                f"Análise estática de {len(nodes)} nós: {len(functions)} função(ões), "
                f"{branch_count} ramo(s) e {len(problems)} observação(ões). "
                "O código não foi executado."
            ),
            line_explanations=lines,
            inputs=tuple(inputs[:100]),
            outputs=outputs,
            invariants=self._invariants(tree),
            constructs=constructs,
            control_flow=tuple(
                (f"linha-{left.lineno}", f"linha-{right.lineno}")
                for left, right in zip(tree.body, tree.body[1:])
            ),
            complexity_time=time_complexity,
            complexity_space="O(n)" if grows_with_input else "O(1)",
            problems=problems,
            suggested_tests=tuple(suggested_tests),
            proposed_code=proposed,
            related_concepts=related,
            confidence=.92 if not problems else .78,
        )

    def _diagnostics(self, source, tree, collector):
        from aprendix.application.contracts.snippet import (
            DiagnosticDTO,
            SnippetDiagnosticSeverity,
        )

        severity = {
            "erro": SnippetDiagnosticSeverity.ERROR,
            "aviso": SnippetDiagnosticSeverity.WARNING,
            "info": SnippetDiagnosticSeverity.INFORMATION,
        }
        results = [
            DiagnosticDTO(
                code=item.code or "python.style",
                severity=severity.get(item.severity, SnippetDiagnosticSeverity.INFORMATION),
                line=max(1, item.line),
                column=max(0, item.column - 1),
                message=item.message,
                evidence=self._source_line(source, item.line),
                confidence=.98,
                safe_fix=item.quick_fix,
            )
            for item in diagnose_python(source)
        ]
        known = set(dir(builtins)) | {"__name__", "__file__", "__package__"}
        undefined_seen: set[tuple[str, int, int]] = set()
        for use in collector.uses:
            resolved = use.scope.resolve(use.name)
            if (
                resolved is not None
                and resolved is use.scope.definitions.get(use.name)
                and use.scope.parent is not None
                and getattr(resolved.node, "lineno", 0) > use.node.lineno
            ):
                results.append(DiagnosticDTO(
                    code="name.used_before_assignment",
                    severity=SnippetDiagnosticSeverity.ERROR,
                    line=use.node.lineno,
                    column=use.node.col_offset,
                    message=f"`{use.name}` é usado antes da atribuição local.",
                    evidence=self._source_line(source, use.node.lineno),
                    confidence=.96,
                    safe_fix="Move a atribuição para antes deste uso ou escolhe explicitamente o âmbito.",
                ))
                continue
            if use.name in known or resolved is not None:
                continue
            key = (use.name, use.node.lineno, use.node.col_offset)
            if key in undefined_seen:
                continue
            undefined_seen.add(key)
            results.append(DiagnosticDTO(
                code="name.undefined",
                severity=SnippetDiagnosticSeverity.ERROR,
                line=use.node.lineno,
                column=use.node.col_offset,
                message=f"O nome `{use.name}` pode não estar definido neste âmbito.",
                evidence=self._source_line(source, use.node.lineno),
                confidence=.9,
                safe_fix="Define ou importa o nome antes deste uso e confirma a grafia.",
            ))
        for scope in collector.scopes:
            for name, definition in scope.definitions.items():
                uses = self._resolved_use_count(collector.uses, definition, scope)
                line = max(1, int(getattr(definition.node, "lineno", 1)))
                column = max(0, int(getattr(definition.node, "col_offset", 0)))
                if name in dir(builtins) and definition.kind not in {"function", "class"}:
                    results.append(DiagnosticDTO(
                        code="name.shadow_builtin",
                        severity=SnippetDiagnosticSeverity.WARNING,
                        line=line,
                        column=column,
                        message=f"`{name}` oculta o built-in com o mesmo nome.",
                        evidence=self._source_line(source, line),
                        confidence=.98,
                        safe_fix=f"Escolhe um nome específico em vez de `{name}`.",
                    ))
                if uses == 0 and not name.startswith("_") and definition.kind in {
                    "variable", "import", "exception"
                }:
                    results.append(DiagnosticDTO(
                        code="name.unused",
                        severity=SnippetDiagnosticSeverity.INFORMATION,
                        line=line,
                        column=column,
                        message=f"`{name}` é definido, mas não é utilizado.",
                        evidence=self._source_line(source, line),
                        confidence=.88,
                    ))
        for statement in ast.walk(tree):
            bodies = [
                value for field_name, value in ast.iter_fields(statement)
                if field_name in {"body", "orelse", "finalbody"} and isinstance(value, list)
            ]
            for body in bodies:
                terminated = False
                for child in body:
                    if terminated:
                        results.append(DiagnosticDTO(
                            code="flow.unreachable",
                            severity=SnippetDiagnosticSeverity.WARNING,
                            line=max(1, getattr(child, "lineno", 1)),
                            column=max(0, getattr(child, "col_offset", 0)),
                            message="Esta instrução é inalcançável no fluxo deste bloco.",
                            evidence=self._source_line(source, getattr(child, "lineno", 1)),
                            confidence=.96,
                        ))
                    if isinstance(child, (ast.Return, ast.Raise, ast.Break, ast.Continue)):
                        terminated = True
        return tuple(self._dedupe_diagnostics(results)[: self._budget.max_diagnostics])

    @staticmethod
    def _resolved_use_count(uses: list[_Use], definition: _Definition, scope: _Scope) -> int:
        return sum(use.scope.resolve(use.name) is definition for use in uses if use.name == definition.name)

    def _symbols(self, collector):
        from aprendix.application.contracts.snippet import SymbolDTO, TypeFactDTO

        symbols, facts = [], []
        for scope in collector.scopes:
            for definition in scope.definitions.values():
                line = max(1, int(getattr(definition.node, "lineno", 1)))
                column = max(0, int(getattr(definition.node, "col_offset", 0)))
                use_count = self._resolved_use_count(collector.uses, definition, scope)
                symbols.append(SymbolDTO(
                    name=definition.name,
                    kind=definition.kind,
                    scope=scope.name,
                    line=line,
                    column=column,
                    use_count=use_count,
                    inferred_type=definition.inferred_type,
                ))
                if definition.inferred_type:
                    facts.append(TypeFactDTO(
                        symbol=f"{scope.name}.{definition.name}",
                        inferred_type=definition.inferred_type,
                        line=line,
                        confidence=.99 if definition.kind == "parameter" else .84,
                        evidence=(
                            "Anotação explícita." if definition.kind == "parameter"
                            else "Inferência conservadora a partir da expressão atribuída."
                        ),
                    ))
        return (
            tuple(sorted(symbols, key=lambda item: (item.line, item.scope, item.name)))[:5_000],
            tuple(sorted(facts, key=lambda item: (item.line, item.symbol)))[:5_000],
        )

    @staticmethod
    def _functions(tree):
        from aprendix.application.contracts.snippet import FunctionDTO

        parent = _parent_map(tree)
        results = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            qual = _qualified_name(node, parent)
            parameters = tuple(
                arg.arg for arg in (
                    *node.args.posonlyargs, *node.args.args,
                    *((node.args.vararg,) if node.args.vararg else ()),
                    *node.args.kwonlyargs,
                    *((node.args.kwarg,) if node.args.kwarg else ()),
                )
            )
            calls = tuple(sorted({_call_name(item.func) for item in _walk_owned(node)
                                  if isinstance(item, ast.Call)}))[:500]
            raises = tuple(sorted({_exception_name(item.exc) for item in _walk_owned(node)
                                   if isinstance(item, ast.Raise)}))[:100]
            signature = f"{node.name}({_safe_unparse(node.args)})"
            if node.returns:
                signature += f" -> {_safe_unparse(node.returns)}"
            results.append(FunctionDTO(
                name=node.name,
                qualified_name=qual,
                signature=signature,
                line=node.lineno,
                end_line=max(node.lineno, getattr(node, "end_lineno", node.lineno)),
                parameters=parameters,
                return_annotation=_safe_unparse(node.returns) if node.returns else None,
                decorators=tuple(_safe_unparse(item) for item in node.decorator_list),
                is_async=isinstance(node, ast.AsyncFunctionDef),
                calls=calls,
                raises=raises,
            ))
        return tuple(sorted(results, key=lambda item: (item.line, item.qualified_name)))[:1_000]

    @staticmethod
    def _classes(tree):
        from aprendix.application.contracts.snippet import ClassDTO

        parent = _parent_map(tree)
        results = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            methods = tuple(
                item.name for item in node.body
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
            attributes = sorted({
                item.attr for item in ast.walk(node)
                if isinstance(item, ast.Attribute) and isinstance(item.ctx, ast.Store)
                and isinstance(item.value, ast.Name) and item.value.id in {"self", "cls"}
            })
            results.append(ClassDTO(
                name=node.name,
                qualified_name=_qualified_name(node, parent),
                line=node.lineno,
                end_line=max(node.lineno, getattr(node, "end_lineno", node.lineno)),
                bases=tuple(_safe_unparse(item) for item in node.bases),
                decorators=tuple(_safe_unparse(item) for item in node.decorator_list),
                methods=methods,
                attributes=tuple(attributes),
            ))
        return tuple(sorted(results, key=lambda item: (item.line, item.qualified_name)))[:500]

    @staticmethod
    def _cfg(tree):
        from aprendix.application.contracts.snippet import CFGBlockDTO

        blocks = list(_CFGBuilder("module").build(tree.body))
        parent = _parent_map(tree)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                blocks.extend(_CFGBuilder(_qualified_name(node, parent)).build(node.body))
        return tuple(CFGBlockDTO(**item) for item in blocks[:10_000])

    @staticmethod
    def _calls(tree):
        from aprendix.application.contracts.snippet import CallEdgeDTO

        parent = _parent_map(tree)
        results = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            owner = _owner_function(node, parent)
            callee = _call_name(node.func)
            results.append(CallEdgeDTO(
                caller=_qualified_name(owner, parent) if owner else "module",
                callee=callee,
                line=max(1, getattr(node, "lineno", 1)),
                dynamic=not isinstance(node.func, (ast.Name, ast.Attribute)),
            ))
        return tuple(results[:5_000])

    @staticmethod
    def _complexity(tree):
        from aprendix.application.contracts.snippet import ComplexityFindingDTO

        parent = _parent_map(tree)
        scopes: list[tuple[str, ast.AST]] = [("module", tree)]
        scopes.extend(
            (_qualified_name(node, parent), node)
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        )
        findings = []
        for name, root in scopes:
            owned = tuple(_walk_owned(root))
            decisions = sum(
                1 for node in owned
                if isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.ExceptHandler,
                                     ast.IfExp, ast.comprehension, ast.Match))
            ) + sum(max(0, len(node.values) - 1) for node in owned if isinstance(node, ast.BoolOp))
            loop_depth = _max_loop_depth(root)
            recursive = any(
                isinstance(node, ast.Call) and _call_name(node.func).split(".")[-1] == name.split(".")[-1]
                for node in owned
            )
            containers = any(isinstance(node, (
                ast.List, ast.Set, ast.Dict, ast.ListComp, ast.SetComp, ast.DictComp,
            )) for node in owned)
            time_class = "O(?) recursivo" if recursive else (
                "O(1)" if loop_depth == 0 else "O(n)" if loop_depth == 1 else f"O(n^{loop_depth})"
            )
            findings.append(ComplexityFindingDTO(
                scope=name,
                cyclomatic=1 + decisions,
                time=time_class,
                space="O(n)" if containers or recursive else "O(1)",
                rationale=(
                    f"Estimativa estrutural: {decisions} ponto(s) de decisão, "
                    f"profundidade máxima de ciclos {loop_depth} e recursão={recursive}."
                ),
            ))
        return tuple(findings[:1_000])

    @staticmethod
    def _security(tree):
        from aprendix.application.contracts.snippet import (
            SecurityFindingDTO,
            SnippetDiagnosticSeverity,
        )

        dangerous = {
            "eval": ("security.dynamic_eval", "Executa texto como expressão Python."),
            "exec": ("security.dynamic_exec", "Executa texto como código Python."),
            "compile": ("security.dynamic_compile", "Compila texto controlável como código."),
            "os.system": ("security.shell", "Inicia um comando através da shell."),
            "subprocess.run": ("security.process", "Inicia um processo externo."),
            "subprocess.call": ("security.process", "Inicia um processo externo."),
            "subprocess.Popen": ("security.process", "Inicia um processo externo."),
            "pickle.loads": ("security.deserialize", "Desserialização pickle pode executar código."),
            "yaml.load": ("security.deserialize", "Carregamento YAML inseguro pode construir objetos."),
        }
        network_prefixes = ("requests.", "urllib.request.", "socket.", "http.client.")
        findings = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _call_name(node.func)
                if name in dangerous:
                    code, message = dangerous[name]
                    findings.append(SecurityFindingDTO(
                        code=code,
                        severity=SnippetDiagnosticSeverity.ERROR,
                        line=max(1, getattr(node, "lineno", 1)),
                        message=message,
                        evidence=f"Chamada estática identificada: {name}(...)",
                    ))
                elif name == "open":
                    findings.append(SecurityFindingDTO(
                        code="security.filesystem",
                        severity=SnippetDiagnosticSeverity.WARNING,
                        line=max(1, getattr(node, "lineno", 1)),
                        message="A chamada tenta aceder ao sistema de ficheiros.",
                        evidence="Chamada estática identificada: open(...)",
                    ))
                elif name.startswith(network_prefixes):
                    findings.append(SecurityFindingDTO(
                        code="security.network",
                        severity=SnippetDiagnosticSeverity.ERROR,
                        line=max(1, getattr(node, "lineno", 1)),
                        message="A chamada tenta aceder à rede, indisponível no sandbox.",
                        evidence=f"Chamada estática identificada: {name}(...)",
                    ))
            if isinstance(node, (ast.Assign, ast.AnnAssign)):
                value = getattr(node, "value", None)
                names = [name.casefold() for target in getattr(node, "targets", (getattr(node, "target", None),))
                         if target is not None for name in _target_names(target)]
                if isinstance(value, ast.Constant) and isinstance(value.value, str) and len(value.value) >= 12 \
                        and any(re.search(r"(?:secret|password|passwd|token|api[_-]?key)", name) for name in names):
                    findings.append(SecurityFindingDTO(
                        code="security.hardcoded_secret",
                        severity=SnippetDiagnosticSeverity.WARNING,
                        line=max(1, getattr(node, "lineno", 1)),
                        message="Possível segredo guardado diretamente no código.",
                        evidence="Nome sensível associado a uma string literal longa.",
                    ))
        return tuple(findings[:500])

    @staticmethod
    def _tests(tree, functions):
        from aprendix.application.contracts.snippet import TestSuggestionDTO

        suggestions = []
        for function in functions[:40]:
            args = ", ".join("None" for _ in function.parameters)
            suggestions.extend((
                TestSuggestionDTO(
                    name=f"{function.name}: caso nominal",
                    rationale="Confirma o contrato com valores representativos do domínio.",
                    category="nominal",
                    code=f"# Ajusta os valores ao contrato observado\nresult = {function.name}({args})\nassert result is not None",
                ),
                TestSuggestionDTO(
                    name=f"{function.name}: fronteira",
                    rationale="Exercita vazio, zero ou o menor valor permitido.",
                    category="boundary",
                    code=f"# Escolhe a fronteira válida para cada parâmetro\n{function.name}({args})",
                ),
            ))
        if any(isinstance(node, (ast.For, ast.While, ast.comprehension)) for node in ast.walk(tree)):
            suggestions.append(TestSuggestionDTO(
                name="Sequência vazia e elemento único",
                rationale="Valida as condições inicial e terminal dos ciclos.",
                category="boundary",
            ))
        if any(isinstance(node, (ast.Div, ast.FloorDiv, ast.Mod)) for node in ast.walk(tree)):
            suggestions.append(TestSuggestionDTO(
                name="Denominador zero",
                rationale="Confirma a política para ZeroDivisionError ou validação explícita.",
                category="exception",
            ))
        if not suggestions:
            suggestions.append(TestSuggestionDTO(
                name="Estado final observável",
                rationale="Compara a saída ou estado produzido com um valor esperado explícito.",
                category="nominal",
            ))
        return tuple(suggestions[:500])

    @staticmethod
    def _imports(tree) -> tuple[str, ...]:
        values = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                values.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                values.append("." * node.level + (node.module or ""))
        return tuple(dict.fromkeys(values))[:500]

    @staticmethod
    def _possible_exceptions(tree) -> tuple[str, ...]:
        values = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Raise):
                values.append(_exception_name(node.exc))
            elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)):
                values.append("ZeroDivisionError")
            elif isinstance(node, ast.Subscript):
                values.extend(("IndexError", "KeyError"))
            elif isinstance(node, ast.Attribute):
                values.append("AttributeError")
            elif isinstance(node, ast.Call) and _call_name(node.func) in {"int", "float"}:
                values.extend(("TypeError", "ValueError"))
        return tuple(dict.fromkeys(value for value in values if value))[:500]

    @staticmethod
    def _inputs(tree, functions) -> tuple[str, ...]:
        values = [
            f"{function.qualified_name}: {parameter}"
            for function in functions for parameter in function.parameters
        ]
        values.extend(
            f"Linha {node.lineno}: input()"
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and _call_name(node.func) == "input"
        )
        return tuple(values[:100])

    @staticmethod
    def _outputs(tree) -> tuple[str, ...]:
        values = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Return):
                values.append(f"Linha {node.lineno}: return {_safe_unparse(node.value)}")
            elif isinstance(node, (ast.Yield, ast.YieldFrom)):
                values.append(f"Linha {node.lineno}: yield {_safe_unparse(node.value)}")
            elif isinstance(node, ast.Call) and _call_name(node.func) == "print":
                values.append(f"Linha {node.lineno}: stdout por print(...)")
        return tuple(values[:100])

    @staticmethod
    def _syntax_diagnostics(source, exc):
        from aprendix.application.contracts.snippet import (
            DiagnosticDTO,
            SnippetDiagnosticSeverity,
        )

        line = max(1, int(exc.lineno or 1))
        return (DiagnosticDTO(
            code="syntax.invalid",
            severity=SnippetDiagnosticSeverity.ERROR,
            line=line,
            column=max(0, int(exc.offset or 1) - 1),
            message=exc.msg or "Sintaxe Python inválida.",
            evidence=SnippetAnalyzer._source_line(source, line),
            confidence=1.0,
            safe_fix="Revê primeiro delimitadores, dois-pontos e indentação nesta linha e na anterior.",
        ),)

    @staticmethod
    def _partial_symbols(source):
        results = []
        for line_no, line in enumerate(source.splitlines(), 1):
            match = re.match(r"\s*(def|class)\s+([A-Za-z_]\w*)", line)
            if match:
                results.append((match.group(2), "function" if match.group(1) == "def" else "class", line_no))
            match = re.match(r"\s*([A-Za-z_]\w*)\s*(?::[^=]+)?=", line)
            if match:
                results.append((match.group(1), "variable", line_no))
        return tuple(dict.fromkeys(results))[:500]

    def _pseudocode(self, request, original, normalized, language, started):
        lines = [line.strip() for line in normalized.splitlines() if line.strip()]
        constructs = []
        for line in lines:
            upper = line.upper()
            if re.match(r"^(SE|IF)\b", upper):
                constructs.append("condition")
            if re.match(r"^(PARA|FOR)\b", upper):
                constructs.append("for-loop")
            if re.match(r"^(ENQUANTO|WHILE)\b", upper):
                constructs.append("while-loop")
            if re.match(r"^(LER|INPUT)\b", upper):
                constructs.append("input")
            if re.match(r"^(ESCREVER|PRINT|RETURN)\b", upper):
                constructs.append("output")
        nested = sum(item in {"for-loop", "while-loop"} for item in constructs)
        action = request.action.value
        proposed = self._to_python(lines) if action == "to_python" else (
            normalized if action in {"complete", "to_algorithm"} else ""
        )
        action_result = {
            "explain": "Explicação por passos, entradas, saídas e estruturas reconhecidas.",
            "complete": "Estrutura preservada; completa os passos marcados sem alterar o objetivo.",
            "to_algorithm": "O texto já está representado como algoritmo estruturado.",
            "to_python": "Conversão estrutural para Python; revê tipos e limites antes de executar no sandbox.",
            "find_problems": "Verificação de estrutura, terminação e entradas/saídas do pseudocódigo.",
            "create_tests": "Casos sugeridos: vazio, unitário, nominal e inválido.",
            "visualize": f"Fluxo sequencial com {max(0, len(lines) - 1)} transição(ões).",
            "link_course": "Ligação recomendada: algoritmia, controlo de fluxo e decomposição top-down.",
        }.get(action, "Análise estrutural concluída.")
        return self._result(
            original=original,
            normalized=normalized,
            detected_language=language,
            summary=(
                "Algoritmo analisado estaticamente, sem execução: "
                f"{constructs.count('condition')} decisão(ões) e {nested} ciclo(s)."
            ),
            line_explanations=tuple(f"Passo {i}: {line}" for i, line in enumerate(lines, 1)),
            inputs=tuple(line for line in lines if re.match(r"^(LER|INPUT)\b", line, re.IGNORECASE)),
            outputs=tuple(line for line in lines if re.match(r"^(ESCREVER|PRINT|RETURN)\b", line, re.IGNORECASE)),
            invariants=("O estado e a condição de progresso devem permanecer válidos em cada repetição.",)
            if nested else (),
            constructs=tuple(dict.fromkeys(constructs)),
            control_flow=tuple((f"passo-{i}", f"passo-{i + 1}") for i in range(1, len(lines))),
            complexity_time=(
                "O(n) provável" if nested == 1 else f"O(n^{nested}) provável" if nested > 1
                else "O(1) provável"
            ),
            complexity_space="O(1) provável",
            problems=(() if constructs else ("Não foram reconhecidas estruturas algorítmicas explícitas.",)),
            suggested_tests=("Entrada vazia", "Um único elemento", "Vários elementos", "Entrada inválida"),
            proposed_code=proposed,
            related_concepts=tuple(dict.fromkeys(constructs)),
            action=request.action,
            action_result=action_result,
            confidence=.84 if constructs else .42,
            elapsed_ms=self._elapsed(started),
        )

    def _result(self, **values):
        if self._result_fields is not None:
            values = {
                key: value for key, value in values.items()
                if key in self._result_fields
            }
        return self._result_type(**values)

    def _cancelled_result(self, request, original, normalized, language, started):
        return self._result(
            original=original,
            normalized=normalized,
            detected_language=language,
            summary="Análise cancelada antes de concluir; nenhum código foi executado.",
            complexity_time="não calculada",
            complexity_space="não calculada",
            problems=("Análise cancelada.",),
            action=request.action,
            action_result="Operação cancelada.",
            confidence=0.0,
            analysis_truncated=True,
            elapsed_ms=self._elapsed(started),
        )

    @staticmethod
    def _cancelled(cancellation) -> bool:
        if cancellation is None:
            return False
        if callable(cancellation):
            return bool(cancellation())
        value = getattr(cancellation, "cancelled", None)
        if value is not None:
            return bool(value() if callable(value) else value)
        is_set = getattr(cancellation, "is_set", None)
        return bool(is_set()) if callable(is_set) else False

    @staticmethod
    def _ast_depth(root: ast.AST) -> int:
        maximum = 0
        stack = [(root, 1)]
        while stack:
            node, depth = stack.pop()
            maximum = max(maximum, depth)
            stack.extend((child, depth + 1) for child in ast.iter_child_nodes(node))
        return maximum

    @staticmethod
    def _invariants(tree):
        return tuple(
            f"Linha {node.lineno}: a condição/progresso do ciclo deve aproximar a terminação."
            for node in ast.walk(tree) if isinstance(node, (ast.For, ast.AsyncFor, ast.While))
        )[:100]

    @staticmethod
    def _concepts(constructs):
        mapping = {
            "For": "iteração", "AsyncFor": "iteração assíncrona",
            "While": "ciclo e terminação", "If": "lógica booleana",
            "FunctionDef": "função e contrato", "AsyncFunctionDef": "função assíncrona",
            "ClassDef": "classe e encapsulamento", "Try": "exceções",
            "ListComp": "compreensão de listas", "Match": "pattern matching",
            "Import": "módulos e dependências", "ImportFrom": "módulos e dependências",
        }
        return tuple(dict.fromkeys(mapping[item] for item in constructs if item in mapping))[:100]

    @staticmethod
    def _proposed_code(action, source, tree):
        if action in {"complete", "to_python"}:
            return source
        if action == "to_algorithm":
            lines = []
            for node in tree.body:
                if isinstance(node, ast.Assign):
                    lines.append(f"DEFINIR {_safe_unparse(node.targets[0])} COMO {_safe_unparse(node.value)}")
                elif isinstance(node, ast.Expr):
                    lines.append(f"EXECUTAR {_safe_unparse(node.value)}")
                else:
                    lines.append(type(node).__name__.upper() + ": " + _safe_unparse(node).splitlines()[0])
            return "\n".join(lines)
        return ""

    @staticmethod
    def _action_result(action, **data):
        value = action.value
        diagnostics = data.get("diagnostics", ())
        symbols = data.get("symbols", ())
        functions = data.get("functions", ())
        cfg = data.get("cfg_blocks", ())
        tests = data.get("tests", ())
        related = data.get("related", ())
        if value == "find_problems":
            errors = sum(getattr(item.severity, "value", "") == "error" for item in diagnostics)
            return f"Foram localizados {len(diagnostics)} diagnóstico(s), incluindo {errors} erro(s)."
        if value == "create_tests":
            return f"Foram derivados {len(tests)} caso(s) de teste a partir dos contratos e ramos observados."
        if value == "visualize":
            return f"O CFG contém {len(cfg)} bloco(s) e {sum(len(item.successors) for item in cfg)} ligação(ões)."
        if value == "link_course":
            return "Circuitos recomendados: " + (", ".join(related) or "fundamentos de Python") + "."
        if value == "complete":
            return "O trecho é sintaticamente completo; a proposta preserva o código e não inventa requisitos."
        if value == "to_algorithm":
            return "Foi produzida uma representação algorítmica estrutural sem executar o trecho."
        if value == "to_python":
            return "O trecho já é Python; foi preservado para revisão antes do sandbox."
        return f"Explicação estrutural de {len(symbols)} símbolo(s) e {len(functions)} função(ões)."

    @staticmethod
    def _line_meaning(line):
        stripped = line.strip()
        if stripped.startswith(("def ", "async def ")):
            return "define uma função e o respetivo contrato de chamada."
        if stripped.startswith("class "):
            return "define um tipo e agrupa estado e comportamento."
        if stripped.startswith(("if ", "elif ", "else:")):
            return "seleciona um ramo através de uma condição."
        if stripped.startswith(("for ", "while ", "async for ")):
            return "repete um bloco mantendo uma condição de progresso."
        if stripped.startswith("return"):
            return "termina a função e entrega um resultado."
        if stripped.startswith(("import ", "from ")):
            return "declara uma dependência sem a executar durante esta análise."
        return "calcula, atribui ou invoca uma operação neste passo."

    @staticmethod
    def _to_python(lines):
        result, indent = [], 0
        for line in lines:
            clean, upper = line.strip(), line.strip().upper()
            if re.match(r"^(FIM|END)\b", upper):
                indent = max(0, indent - 1)
                continue
            clean = re.sub(r"^ESCREVER\s+", "print(", clean, flags=re.IGNORECASE)
            if clean.startswith("print(") and not clean.endswith(")"):
                clean += ")"
            clean = re.sub(r"^LER\s+(\w+)", r"\1 = input()", clean, flags=re.IGNORECASE)
            clean = re.sub(r"^SE\s+(.+?)\s+ENTAO$", r"if \1:", clean, flags=re.IGNORECASE)
            clean = re.sub(r"^SENAO$", "else:", clean, flags=re.IGNORECASE)
            if clean == "else:":
                indent = max(0, indent - 1)
            result.append("    " * indent + clean)
            if clean.endswith(":"):
                indent += 1
        return "\n".join(result)

    @staticmethod
    def _source_line(source: str, line: int) -> str:
        lines = source.splitlines()
        return lines[line - 1][:2_000] if 1 <= line <= len(lines) else ""

    @staticmethod
    def _dedupe_diagnostics(items):
        result, seen = [], set()
        for item in items:
            key = (item.code, item.line, item.column, item.message)
            if key not in seen:
                seen.add(key)
                result.append(item)
        return result

    @staticmethod
    def _elapsed(started: float) -> float:
        return (time.perf_counter() - started) * 1_000


def _safe_unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)[:2_000]
    except (ValueError, TypeError, RecursionError):
        return type(node).__name__


def _target_names(node: ast.AST) -> tuple[str, ...]:
    if isinstance(node, ast.Name):
        return (node.id,)
    if isinstance(node, (ast.Tuple, ast.List)):
        return tuple(name for item in node.elts for name in _target_names(item))
    return ()


def _infer_expression_type(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant):
        return type(node.value).__name__
    names = {
        ast.List: "list", ast.Tuple: "tuple", ast.Set: "set", ast.Dict: "dict",
        ast.ListComp: "list", ast.SetComp: "set", ast.DictComp: "dict",
        ast.GeneratorExp: "generator", ast.Lambda: "callable",
    }
    for kind, name in names.items():
        if isinstance(node, kind):
            return name
    if isinstance(node, ast.Call):
        call = _call_name(node.func)
        if call in {"int", "float", "str", "bool", "list", "tuple", "set", "dict", "bytes"}:
            return call
        return f"return of {call}" if call else None
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Div):
            return "float"
        left, right = _infer_expression_type(node.left), _infer_expression_type(node.right)
        return left if left == right else None
    if isinstance(node, ast.Compare):
        return "bool"
    return None


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _call_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return _safe_unparse(node)


def _exception_name(node: ast.AST | None) -> str:
    if isinstance(node, ast.Call):
        return _call_name(node.func)
    return _safe_unparse(node) or "BaseException"


def _parent_map(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def _owner_function(node: ast.AST, parent: dict[ast.AST, ast.AST]):
    current = parent.get(node)
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current
        current = parent.get(current)
    return None


def _qualified_name(node: ast.AST, parent: dict[ast.AST, ast.AST]) -> str:
    names = [getattr(node, "name", type(node).__name__)]
    current = parent.get(node)
    while current is not None:
        if isinstance(current, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.append(current.name)
        current = parent.get(current)
    return ".".join(reversed(names))


def _walk_owned(root: ast.AST):
    stack = [root]
    first = True
    while stack:
        node = stack.pop()
        yield node
        if not first and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        first = False
        stack.extend(reversed(list(ast.iter_child_nodes(node))))


def _max_loop_depth(root: ast.AST) -> int:
    maximum = 0
    stack = [(root, 0)]
    first = True
    while stack:
        node, depth = stack.pop()
        if not first and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)):
            continue
        first = False
        next_depth = depth + int(isinstance(node, (ast.For, ast.AsyncFor, ast.While, ast.comprehension)))
        maximum = max(maximum, next_depth)
        stack.extend((child, next_depth) for child in ast.iter_child_nodes(node))
    return maximum
