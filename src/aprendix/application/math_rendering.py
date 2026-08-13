"""Toolkit-neutral contracts for safe, local mathematical rendering."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True, slots=True)
class FormulaRenderRequest:
    """A bounded mathematical expression and its accessible explanation."""

    latex: str
    spoken: str
    variables: Mapping[str, str]
    theme: str = "dark"
    dpi: int = 144
    scale: float = 1.0


@dataclass(frozen=True, slots=True)
class FormulaRenderResult:
    """A content-addressed local image plus the non-visual alternatives."""

    path: Path | None
    spoken: str
    latex: str
    variables: tuple[tuple[str, str], ...]
    backend: str
    cache_key: str
    error: str = ""


class MathRendererPort(Protocol):
    """Render a safe LaTeX subset without network or external processes."""

    def render(self, request: FormulaRenderRequest) -> FormulaRenderResult: ...
