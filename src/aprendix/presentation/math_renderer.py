"""Bounded offline mathematical rendering with a content-addressed cache."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from aprendix.application.math_rendering import (
    FormulaRenderRequest,
    FormulaRenderResult,
)
from aprendix.presentation.text_safety import normalize_ui_text

RENDERER_VERSION = "aprendix-math-v3"
MAX_LATEX_LENGTH = 2_048
MAX_BRACE_DEPTH = 16
_COMMAND_RE = re.compile(r"\\([A-Za-z]+)")
_ALLOWED_COMMANDS = frozenset({
    "alpha", "beta", "gamma", "delta", "epsilon", "theta", "lambda", "mu",
    "pi", "rho", "sigma", "tau", "phi", "omega", "Gamma", "Delta", "Theta",
    "Lambda", "Pi", "Sigma", "Phi", "Omega", "frac", "sqrt", "sum", "prod",
    "int", "lim", "log", "ln", "sin", "cos", "tan", "exp", "cdot", "times",
    "div", "pm", "le", "leq", "ge", "geq", "ne", "neq", "approx", "infty",
    "left", "right", "begin", "end", "matrix", "pmatrix", "bmatrix", "text",
    "mathrm", "mathbf", "mathit", "overline", "hat", "vec", "partial", "nabla",
})
_FORBIDDEN_FRAGMENTS = (
    "\\write", "\\input", "\\include", "\\openout", "\\read", "\\catcode",
    "\\csname", "\\def", "\\newcommand", "\\usepackage", "\\href", "\\url",
)


class FormulaValidationError(ValueError):
    """Raised when a formula exceeds the deliberately small safe subset."""


def validate_latex(latex: str) -> str:
    value = normalize_ui_text(latex).strip()
    if not value:
        raise FormulaValidationError("A fórmula está vazia.")
    if len(value) > MAX_LATEX_LENGTH:
        raise FormulaValidationError("A fórmula excede o limite local de 2048 caracteres.")
    lowered = value.casefold()
    if any(fragment in lowered for fragment in _FORBIDDEN_FRAGMENTS):
        raise FormulaValidationError("A fórmula contém um comando não permitido.")
    depth = maximum = 0
    for character in value:
        if character == "{":
            depth += 1
            maximum = max(maximum, depth)
        elif character == "}":
            depth -= 1
            if depth < 0:
                raise FormulaValidationError("A fórmula tem chavetas desequilibradas.")
    if depth or maximum > MAX_BRACE_DEPTH:
        raise FormulaValidationError("A fórmula tem chavetas desequilibradas ou demasiado profundas.")
    # A matrix row break is ``\\``. Without removing that token first, the
    # generic command scanner reads ``\\c`` (row break followed by cell ``c``)
    # as the nonexistent command ``\c``. Forbidden host-capable fragments were
    # checked above on the untouched expression, so this normalization cannot
    # be used to bypass the security policy.
    command_source = value.replace("\\\\", " ")
    unknown = sorted(set(_COMMAND_RE.findall(command_source)) - _ALLOWED_COMMANDS)
    if unknown:
        raise FormulaValidationError("Comando matemático não permitido: " + unknown[0])
    return value


def formula_cache_key(request: FormulaRenderRequest) -> str:
    payload = {
        "dpi": int(request.dpi),
        "latex": validate_latex(request.latex),
        "renderer": RENDERER_VERSION,
        "scale": round(float(request.scale), 3),
        "theme": request.theme,
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def default_math_cache_dir() -> Path:
    local_data = os.environ.get("LOCALAPPDATA")
    root = Path(local_data) if local_data else Path(tempfile.gettempdir())
    return root / "Aprendix" / "cache" / "math"


class OfflineMathRenderer:
    """Use MathText/Agg when present, with a deterministic Pillow fallback."""

    def __init__(self, cache_dir: Path | None = None) -> None:
        self.cache_dir = Path(cache_dir) if cache_dir is not None else default_math_cache_dir()

    def render(self, request: FormulaRenderRequest) -> FormulaRenderResult:
        spoken = normalize_ui_text(request.spoken) or "Expressão matemática"
        variables = tuple(
            (normalize_ui_text(name), normalize_ui_text(meaning))
            for name, meaning in request.variables.items()
        )
        try:
            latex = validate_latex(request.latex)
            key = formula_cache_key(request)
        except FormulaValidationError as exc:
            return FormulaRenderResult(
                path=None, spoken=spoken, latex=normalize_ui_text(request.latex),
                variables=variables, backend="accessible-fallback", cache_key="",
                error=str(exc),
            )
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        target = self.cache_dir / f"{key}.png"
        if target.is_file() and target.stat().st_size > 0:
            return FormulaRenderResult(
                path=target, spoken=spoken, latex=latex, variables=variables,
                backend="cache", cache_key=key,
            )
        try:
            self._render_mathtext(target, latex, request)
            backend = "mathtext-agg"
        except (ImportError, ModuleNotFoundError, RuntimeError, ValueError, OSError):
            try:
                self._render_pillow(target, latex, request)
                backend = "pillow-local"
            except (ImportError, ModuleNotFoundError, RuntimeError, ValueError, OSError) as exc:
                return FormulaRenderResult(
                    path=None, spoken=spoken, latex=latex, variables=variables,
                    backend="accessible-fallback", cache_key=key,
                    error=f"Não foi possível compor a fórmula localmente: {exc}",
                )
        return FormulaRenderResult(
            path=target, spoken=spoken, latex=latex, variables=variables,
            backend=backend, cache_key=key,
        )

    @staticmethod
    def _render_mathtext(target: Path, latex: str, request: FormulaRenderRequest) -> None:
        from matplotlib import mathtext
        from PIL import Image

        foreground_rgb = (
            (255, 255, 255) if request.theme in {"dark", "contrast"}
            else (17, 24, 39)
        )
        # MathText names these comparison glyphs with their long aliases even
        # though the short forms are conventional in teaching material.
        mathtext_latex = re.sub(r"\\le\b", r"\\leq", latex)
        mathtext_latex = re.sub(r"\\ge\b", r"\\geq", mathtext_latex)
        mathtext_latex = re.sub(r"\\ne\b", r"\\neq", mathtext_latex)
        expression = (
            mathtext_latex if mathtext_latex.startswith("$") and mathtext_latex.endswith("$")
            else f"${mathtext_latex}$"
        )
        temporary = target.with_suffix(".mathtext.png")
        mathtext.math_to_image(
            expression, str(temporary), dpi=max(72, min(384, int(request.dpi))),
            format="png", color="#000000",
        )
        # MathText writes an opaque white background. Convert only background
        # pixels connected to that white to transparent so dark-theme glyphs
        # remain visible when Kivy composites the image over its card.
        image = Image.open(temporary).convert("RGBA")
        pixels = []
        for red, green, blue, alpha in image.getdata():
            darkness = max(0, min(255, 255 - max(red, green, blue)))
            pixels.append((*foreground_rgb, min(alpha, darkness)))
        image.putdata(pixels)
        output = target.with_suffix(".tmp.png")
        image.save(output, format="PNG", optimize=True)
        output.replace(target)
        temporary.unlink(missing_ok=True)

    @staticmethod
    def _render_pillow(target: Path, latex: str, request: FormulaRenderRequest) -> None:
        from PIL import Image, ImageDraw

        plain = latex_to_readable_unicode(latex)
        scale = min(2.5, max(.75, float(request.scale)))
        size = max(18, round(27 * scale * max(1.0, request.dpi / 144)))
        font = _local_math_font(size)
        foreground = (255, 255, 255, 255) if request.theme in {"dark", "contrast"} else (17, 24, 39, 255)
        probe = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        bounds = ImageDraw.Draw(probe).multiline_textbbox((0, 0), plain, font=font, spacing=8)
        width = min(3_200, max(120, bounds[2] - bounds[0] + 36))
        height = min(1_200, max(58, bounds[3] - bounds[1] + 32))
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        ImageDraw.Draw(image).multiline_text((18, 14), plain, fill=foreground, font=font, spacing=8)
        temporary = target.with_suffix(".tmp.png")
        image.save(temporary, format="PNG", optimize=True)
        temporary.replace(target)


_SYMBOLS = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε",
    "theta": "θ", "lambda": "λ", "mu": "μ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "phi": "φ", "omega": "ω", "Gamma": "Γ",
    "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Pi": "Π", "Sigma": "Σ",
    "Phi": "Φ", "Omega": "Ω", "sum": "∑", "prod": "∏", "int": "∫",
    "cdot": "·", "times": "×", "div": "÷", "pm": "±", "le": "≤",
    "leq": "≤", "ge": "≥", "geq": "≥", "ne": "≠", "neq": "≠",
    "approx": "≈", "infty": "∞", "partial": "∂", "nabla": "∇",
}


def latex_to_readable_unicode(latex: str) -> str:
    """Produce a legible local fallback without exposing LaTeX commands."""

    value = validate_latex(latex).strip("$")
    fraction = re.compile(r"\\frac\{([^{}]+)\}\{([^{}]+)\}")
    for _ in range(8):
        updated = fraction.sub(lambda match: f"({match.group(1)})⁄({match.group(2)})", value)
        if updated == value:
            break
        value = updated
    value = re.sub(r"\\sqrt\{([^{}]+)\}", lambda match: f"√({match.group(1)})", value)
    value = re.sub(
        r"\\(?:text|mathrm|mathbf|mathit|overline|hat|vec)\{([^{}]+)\}",
        lambda match: match.group(1), value,
    )
    for command, symbol in sorted(_SYMBOLS.items(), key=lambda item: -len(item[0])):
        value = re.sub(rf"\\{re.escape(command)}\b", symbol, value)
    value = re.sub(r"\\(?:left|right)\b", "", value)
    value = value.replace("\\begin{matrix}", "[").replace("\\end{matrix}", "]")
    value = value.replace("\\begin{pmatrix}", "(").replace("\\end{pmatrix}", ")")
    value = value.replace("\\begin{bmatrix}", "[").replace("\\end{bmatrix}", "]")
    value = value.replace("\\\\", "\n").replace("&", "   ")
    value = re.sub(r"_\{([^{}]+)\}", lambda match: f"₍{match.group(1)}₎", value)
    value = re.sub(r"\^\{([^{}]+)\}", lambda match: f"^({match.group(1)})", value)
    value = value.replace("{", "").replace("}", "")
    value = re.sub(r"\\[A-Za-z]+", "", value)
    return re.sub(r"[ \t]+", " ", value).strip()


_DISPLAY_FORMULA_RE = re.compile(r"\$\$(.{1,2048}?)\$\$", re.DOTALL)
_INLINE_FORMULA_RE = re.compile(r"(?<!\$)\$(?!\$)(.{1,1024}?)(?<!\$)\$(?!\$)")
_PAREN_FORMULA_RE = re.compile(r"\\\((.{1,1024}?)\\\)")


def extract_latex_expressions(value: str, *, limit: int = 4) -> tuple[str, ...]:
    """Extract bounded explicit formulas from human-facing rich text."""

    if limit < 1:
        return ()
    text = normalize_ui_text(value)
    found: list[str] = []
    for pattern in (_DISPLAY_FORMULA_RE, _PAREN_FORMULA_RE, _INLINE_FORMULA_RE):
        for match in pattern.finditer(text):
            candidate = match.group(1).strip()
            try:
                candidate = validate_latex(candidate)
            except FormulaValidationError:
                continue
            if candidate not in found:
                found.append(candidate)
            if len(found) >= limit:
                return tuple(found)
    return tuple(found)


def strip_latex_markup(
    value: str, explicit_expressions: tuple[str, ...] = (),
) -> str:
    """Hide explicit source markup when a FormulaView renders the expression."""

    text = normalize_ui_text(value)
    for pattern in (_DISPLAY_FORMULA_RE, _PAREN_FORMULA_RE, _INLINE_FORMULA_RE):
        text = pattern.sub("", text)
    for expression in explicit_expressions:
        clean = normalize_ui_text(expression).strip()
        if clean:
            text = text.replace("Notação para copiar: " + clean, "")
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _local_math_font(size: int):
    from PIL import ImageFont

    candidates = (
        Path(__file__).resolve().parent / "assets" / "DejaVuSans.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "segoeui.ttf",
        Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts" / "arial.ttf",
    )
    try:
        import kivy

        candidates += (Path(kivy.__file__).resolve().parent / "data" / "fonts" / "Roboto-Regular.ttf",)
    except (ImportError, AttributeError):
        pass
    try:
        from matplotlib import get_data_path

        candidates += (Path(get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf",)
    except (ImportError, ModuleNotFoundError):
        pass
    for candidate in candidates:
        if candidate.is_file():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()
