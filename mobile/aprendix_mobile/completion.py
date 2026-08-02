"""Explicit structural completion chips; never supplies solution logic."""

from __future__ import annotations

import ast
import io
import keyword
import tokenize


class MobileCompletion:
    _STRUCTURE = ("def", "class", "if", "else", "elif", "for", "while", "return", "print")

    def suggestions(self, source: str, cursor: int, *, limit: int = 8) -> tuple[str, ...]:
        cursor = max(0, min(cursor, len(source)))
        if self._inside_text_or_comment(source, cursor):
            return ()
        prefix = self._prefix(source, cursor)
        declared: set[str] = set()
        try:
            tree = ast.parse(source or "pass")
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                    declared.add(node.name)
                elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                    declared.add(node.id)
        except SyntaxError:
            pass
        candidates = sorted(declared) + list(self._STRUCTURE)
        return tuple(
            item for item in dict.fromkeys(candidates)
            if (not prefix or item.startswith(prefix)) and item != prefix
        )[:limit]

    @staticmethod
    def _prefix(source: str, cursor: int) -> str:
        index = cursor
        while index > 0 and (source[index - 1].isalnum() or source[index - 1] == "_"):
            index -= 1
        return source[index:cursor]

    @staticmethod
    def _inside_text_or_comment(source: str, cursor: int) -> bool:
        try:
            for token in tokenize.generate_tokens(io.StringIO(source).readline):
                if token.type not in (tokenize.STRING, tokenize.COMMENT):
                    continue
                lines = source.splitlines(keepends=True)
                start = sum(len(line) for line in lines[: token.start[0] - 1]) + token.start[1]
                end = sum(len(line) for line in lines[: token.end[0] - 1]) + token.end[1]
                if start <= cursor <= end:
                    return True
        except (tokenize.TokenError, IndentationError):
            return False
        return False

    @staticmethod
    def insert(source: str, cursor: int, token: str) -> tuple[str, int]:
        if not (token.isidentifier() or keyword.iskeyword(token)):
            raise ValueError("completion token is not structural")
        prefix = MobileCompletion._prefix(source, cursor)
        start = cursor - len(prefix)
        updated = source[:start] + token + source[cursor:]
        return updated, start + len(token)

