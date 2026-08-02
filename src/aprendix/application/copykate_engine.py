"""Deterministic CopyKate algorithms for edit imitation and code synthesis."""

from __future__ import annotations

import ast
import copy
import io
import math
import re
import token
import tokenize
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from typing import Any

from aprendix.application.contracts.copykate import (
    AlternativeSolutionDTO,
    AstChangeDTO,
    CodeEditDTO,
    ImitationProfileDTO,
    NGramTransitionDTO,
)

_IGNORED_TOKEN_TYPES = {
    token.ENDMARKER,
    token.ENCODING,
    token.INDENT,
    token.DEDENT,
    token.NEWLINE,
    tokenize.NL,
    tokenize.COMMENT,
}


class CopyKateSyntaxError(ValueError):
    """Raised when CopyKate cannot safely transform invalid Python."""


def _tokens(source: str) -> tuple[str, ...]:
    try:
        generated = tokenize.generate_tokens(io.StringIO(source).readline)
        return tuple(
            item.string[:200]
            for item in generated
            if item.type not in _IGNORED_TOKEN_TYPES and item.string
        )
    except (IndentationError, tokenize.TokenError):
        return ()


def _changed_token_runs(edit: CodeEditDTO) -> tuple[tuple[str, ...], ...]:
    before = _tokens(edit.before)
    after = _tokens(edit.after)
    matcher = SequenceMatcher(a=before, b=after, autojunk=False)
    runs: list[tuple[str, ...]] = []
    for operation, _, _, after_start, after_end in matcher.get_opcodes():
        if operation in {"insert", "replace"} and after_start != after_end:
            prefix_start = max(0, after_start - 4)
            runs.append(after[prefix_start:after_end])
    return tuple(runs)


def _indent_width(sources: tuple[str, ...]) -> int:
    widths = [
        len(line) - len(line.lstrip(" "))
        for source in sources
        for line in source.splitlines()
        if line.startswith(" ") and line.strip()
    ]
    if not widths:
        return 4
    result = widths[0]
    for width in widths[1:]:
        result = math.gcd(result, width)
    return min(max(result, 1), 8)


def _quote_style(sources: tuple[str, ...]) -> str:
    single = 0
    double = 0
    for source in sources:
        try:
            items = tokenize.generate_tokens(io.StringIO(source).readline)
            for item in items:
                if item.type != token.STRING:
                    continue
                literal = re.sub(r"(?i)^[rubf]+", "", item.string)
                if literal.startswith("'"):
                    single += 1
                elif literal.startswith('"'):
                    double += 1
        except (IndentationError, tokenize.TokenError):
            continue
    return "double" if double > single else "single"


def _identifier_style(sources: tuple[str, ...]) -> str:
    snake = 0
    camel = 0
    for source in sources:
        try:
            items = tokenize.generate_tokens(io.StringIO(source).readline)
            for item in items:
                if item.type != token.NAME or not item.string.isidentifier():
                    continue
                if "_" in item.string.strip("_"):
                    snake += 1
                elif re.search(r"[a-z][A-Z]", item.string):
                    camel += 1
        except (IndentationError, tokenize.TokenError):
            continue
    if snake and camel:
        return "mixed"
    if camel:
        return "camelCase"
    return "snake_case"


class EditNGramImitator:
    """Learn next-token preferences from the portions a learner changed."""

    def build_profile(
        self,
        edits: tuple[CodeEditDTO, ...],
        *,
        fallback_source: str,
        order: int,
    ) -> ImitationProfileDTO:
        if not 2 <= order <= 5:
            raise ValueError("order must be between 2 and 5")

        runs = [
            run
            for edit in edits
            for run in _changed_token_runs(edit)
            if len(run) >= order
        ]
        fallback_used = not runs
        if fallback_used:
            fallback_tokens = _tokens(fallback_source)
            runs = [fallback_tokens] if len(fallback_tokens) >= order else []

        counts: dict[tuple[str, ...], Counter[str]] = defaultdict(Counter)
        context_size = order - 1
        for run in runs:
            for index in range(context_size, len(run)):
                context = run[index - context_size : index]
                counts[context][run[index]] += 1

        ranked: list[tuple[int, tuple[str, ...], str, int, float]] = []
        for context, successors in counts.items():
            total = sum(successors.values())
            for next_token, count in successors.items():
                ranked.append(
                    (count, context, next_token, total, count / total)
                )
        ranked.sort(key=lambda item: (-item[0], item[1], item[2]))
        transitions = tuple(
            NGramTransitionDTO(
                context=context,
                next_token=next_token,
                count=count,
                probability=probability,
            )
            for count, context, next_token, _, probability in ranked[:500]
        )
        sources = tuple(edit.after for edit in edits) or (fallback_source,)
        return ImitationProfileDTO(
            ngram_order=order,
            transitions=transitions,
            indent_width=_indent_width(sources),
            quote_style=_quote_style(sources),
            identifier_style=_identifier_style(sources),
            fallback_used=fallback_used,
        )


def _short(value: Any) -> str:
    rendered = repr(value)
    return rendered if len(rendered) <= 2_000 else rendered[:1_997] + "..."


def diff_asts(before: ast.AST, after: ast.AST) -> tuple[AstChangeDTO, ...]:
    """Return a bounded, field-addressed structural AST change log."""

    changes: list[AstChangeDTO] = []

    def add_change(
        kind: str,
        path: str,
        left: Any = None,
        right: Any = None,
    ) -> None:
        if len(changes) >= 250:
            return
        changes.append(
            AstChangeDTO(
                kind=kind,
                path=path,
                before=None if kind == "add" else _short(left),
                after=None if kind == "remove" else _short(right),
            )
        )

    def compare(left: Any, right: Any, path: str) -> None:
        if len(changes) >= 250:
            return
        if isinstance(left, ast.AST) and isinstance(right, ast.AST):
            if type(left) is not type(right):
                add_change(
                    "replace",
                    path,
                    ast.dump(left, include_attributes=False),
                    ast.dump(right, include_attributes=False),
                )
                return
            for field in left._fields:
                compare(
                    getattr(left, field),
                    getattr(right, field),
                    f"{path}.{field}",
                )
            return
        if isinstance(left, list) and isinstance(right, list):
            common = min(len(left), len(right))
            for index in range(common):
                compare(left[index], right[index], f"{path}[{index}]")
            for index in range(common, len(left)):
                add_change("remove", f"{path}[{index}]", left[index])
            for index in range(common, len(right)):
                add_change("add", f"{path}[{index}]", right=right[index])
            return
        if left != right:
            add_change("replace", path, left, right)

    compare(before, after, "Module")
    return tuple(changes)


def _unique_helper_name(tree: ast.AST, preferred: str) -> str:
    used = {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }
    used.update(
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    )
    candidate = preferred
    suffix = 2
    while candidate in used:
        candidate = f"{preferred}_{suffix}"
        suffix += 1
    return candidate


def _helper_arguments(arguments: ast.arguments) -> ast.arguments:
    result = copy.deepcopy(arguments)
    result.defaults = []
    result.kw_defaults = [None for _ in result.kwonlyargs]
    for argument in (
        *result.posonlyargs,
        *result.args,
        *result.kwonlyargs,
    ):
        argument.annotation = None
    if result.vararg is not None:
        result.vararg.annotation = None
    if result.kwarg is not None:
        result.kwarg.annotation = None
    return result


def _helper_call(name: str, arguments: ast.arguments) -> ast.Call:
    positional: list[ast.expr] = [
        ast.Name(id=argument.arg, ctx=ast.Load())
        for argument in (*arguments.posonlyargs, *arguments.args)
    ]
    if arguments.vararg is not None:
        positional.append(
            ast.Starred(
                value=ast.Name(id=arguments.vararg.arg, ctx=ast.Load()),
                ctx=ast.Load(),
            )
        )
    keywords = [
        ast.keyword(
            arg=argument.arg,
            value=ast.Name(id=argument.arg, ctx=ast.Load()),
        )
        for argument in arguments.kwonlyargs
    ]
    if arguments.kwarg is not None:
        keywords.append(
            ast.keyword(
                arg=None,
                value=ast.Name(id=arguments.kwarg.arg, ctx=ast.Load()),
            )
        )
    return ast.Call(func=ast.Name(id=name, ctx=ast.Load()), args=positional, keywords=keywords)


def _docstring_statement(function: ast.FunctionDef) -> ast.Expr | None:
    if (
        function.body
        and isinstance(function.body[0], ast.Expr)
        and isinstance(function.body[0].value, ast.Constant)
        and isinstance(function.body[0].value.value, str)
    ):
        return copy.deepcopy(function.body[0])
    return None


def _nested_helper_variant(
    tree: ast.Module,
    function_index: int,
    helper_name: str,
) -> ast.Module:
    result = copy.deepcopy(tree)
    function = result.body[function_index]
    assert isinstance(function, ast.FunctionDef)
    nested = ast.FunctionDef(
        name=helper_name,
        args=_helper_arguments(function.args),
        body=copy.deepcopy(function.body),
        decorator_list=[],
        returns=None,
        type_comment=None,
    )
    body: list[ast.stmt] = []
    docstring = _docstring_statement(function)
    if docstring is not None:
        body.append(docstring)
    body.extend(
        [
            nested,
            ast.Return(value=_helper_call(helper_name, function.args)),
        ]
    )
    function.body = body
    ast.fix_missing_locations(result)
    return result


def _extracted_helper_variant(
    tree: ast.Module,
    function_index: int,
    helper_name: str,
) -> ast.Module:
    result = copy.deepcopy(tree)
    function = result.body[function_index]
    assert isinstance(function, ast.FunctionDef)
    helper = ast.FunctionDef(
        name=helper_name,
        args=_helper_arguments(function.args),
        body=copy.deepcopy(function.body),
        decorator_list=[],
        returns=None,
        type_comment=None,
    )
    wrapper_body: list[ast.stmt] = []
    docstring = _docstring_statement(function)
    if docstring is not None:
        wrapper_body.append(docstring)
    wrapper_body.append(
        ast.Return(value=_helper_call(helper_name, function.args))
    )
    function.body = wrapper_body
    result.body.insert(function_index, helper)
    ast.fix_missing_locations(result)
    return result


def _script_variant(
    tree: ast.Module,
    helper_name: str,
    *,
    extracted: bool,
) -> ast.Module:
    original_body = copy.deepcopy(tree.body)
    if extracted:
        body_helper = ast.FunctionDef(
            name=f"{helper_name}_body",
            args=ast.arguments(
                posonlyargs=[],
                args=[],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=original_body,
            decorator_list=[],
        )
        entry = ast.FunctionDef(
            name=helper_name,
            args=copy.deepcopy(body_helper.args),
            body=[
                ast.Return(
                    value=ast.Call(
                        func=ast.Name(id=body_helper.name, ctx=ast.Load()),
                        args=[],
                        keywords=[],
                    )
                )
            ],
            decorator_list=[],
        )
        result = ast.Module(
            body=[
                body_helper,
                entry,
                ast.Expr(
                    value=ast.Call(
                        func=ast.Name(id=helper_name, ctx=ast.Load()),
                        args=[],
                        keywords=[],
                    )
                ),
            ],
            type_ignores=[],
        )
    else:
        entry = ast.FunctionDef(
            name=helper_name,
            args=ast.arguments(
                posonlyargs=[],
                args=[],
                kwonlyargs=[],
                kw_defaults=[],
                defaults=[],
            ),
            body=original_body,
            decorator_list=[],
        )
        result = ast.Module(
            body=[
                entry,
                ast.Expr(
                    value=ast.Call(
                        func=ast.Name(id=helper_name, ctx=ast.Load()),
                        args=[],
                        keywords=[],
                    )
                ),
            ],
            type_ignores=[],
        )
    ast.fix_missing_locations(result)
    return result


class AlternativeSynthesizer:
    """Produce three parseable, deterministic structural alternatives."""

    def synthesize(
        self,
        source_code: str,
        profile: ImitationProfileDTO,
    ) -> tuple[
        AlternativeSolutionDTO,
        AlternativeSolutionDTO,
        AlternativeSolutionDTO,
    ]:
        try:
            original_tree = ast.parse(source_code, mode="exec")
        except SyntaxError as exc:
            location = f"line {exc.lineno}, column {exc.offset}"
            raise CopyKateSyntaxError(f"invalid Python at {location}: {exc.msg}") from exc

        canonical_tree = copy.deepcopy(original_tree)
        ast.fix_missing_locations(canonical_tree)
        function_index = next(
            (
                index
                for index, statement in enumerate(original_tree.body)
                if isinstance(statement, ast.FunctionDef)
                and not any(
                    isinstance(node, (ast.Yield, ast.YieldFrom, ast.Nonlocal, ast.Global))
                    for node in ast.walk(statement)
                )
            ),
            None,
        )
        stem = (
            "copykateCompute"
            if profile.identifier_style == "camelCase"
            else "copykate_compute"
        )
        nested_name = _unique_helper_name(original_tree, stem)
        extracted_name = _unique_helper_name(
            original_tree,
            f"{stem}Alternative"
            if profile.identifier_style == "camelCase"
            else f"{stem}_alternative",
        )

        if function_index is None:
            nested_tree = _script_variant(
                original_tree,
                nested_name,
                extracted=False,
            )
            extracted_tree = _script_variant(
                original_tree,
                extracted_name,
                extracted=True,
            )
        else:
            nested_tree = _nested_helper_variant(
                original_tree,
                function_index,
                nested_name,
            )
            extracted_tree = _extracted_helper_variant(
                original_tree,
                function_index,
                extracted_name,
            )

        variants = (
            (
                "canonical",
                canonical_tree,
                "Normalizes the learner's solution without changing its AST structure; "
                f"the learned profile prefers {profile.indent_width}-space indentation "
                f"and {profile.quote_style} quotes.",
            ),
            (
                "nested_helper",
                nested_tree,
                "Keeps the public entry point and moves its computation into a local "
                "helper, making the execution stages explicit while retaining closure scope.",
            ),
            (
                "extracted_helper",
                extracted_tree,
                "Separates computation from the public entry point so the core logic can "
                "be tested independently and the wrapper remains small.",
            ),
        )
        alternatives: list[AlternativeSolutionDTO] = []
        for strategy, variant_tree, justification in variants:
            rendered = ast.unparse(variant_tree).rstrip() + "\n"
            reparsed = ast.parse(rendered, mode="exec")
            alternatives.append(
                AlternativeSolutionDTO(
                    strategy=strategy,
                    source_code=rendered,
                    justification=justification,
                    ast_changes=diff_asts(original_tree, reparsed),
                )
            )
        return alternatives[0], alternatives[1], alternatives[2]
