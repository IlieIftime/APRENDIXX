"""Bounded, loss-aware text decoding for prose, code, Web and OCR inputs.

The service deliberately refuses undecodable input instead of hiding damage with
U+FFFD.  It has no network or execution side effects and is safe to use before
content enters the encrypted catalogue.
"""

from __future__ import annotations

import io
import re
import tokenize
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from html import unescape


class TextProfile(str, Enum):
    PROSE = "prose"
    PYTHON = "python"
    NOTEBOOK = "notebook"
    FORMULA = "formula"
    WEB = "web"
    OCR = "ocr"


class TextDecodingError(ValueError):
    """Raised when decoding would require silent, irreversible substitution."""


@dataclass(frozen=True, slots=True)
class NormalizedText:
    text: str
    encoding: str
    profile: TextProfile
    repaired_mojibake: bool = False
    anomaly_score: int = 0
    warnings: tuple[str, ...] = ()
    original: str = ""
    confidence: float | None = None


class TextNormalizationService:
    MAX_BYTES = 2_000_000
    _META_CHARSET = re.compile(
        br"<meta\s+[^>]*(?:charset\s*=\s*['\"]?\s*([a-zA-Z0-9._-]+)|"
        br"content\s*=\s*['\"][^'\"]*charset\s*=\s*([a-zA-Z0-9._-]+))",
        re.IGNORECASE,
    )
    _MOJIBAKE = re.compile(r"(?:Ã.|Â.|â(?:€|€™|€œ|€|€“|€”|†|‡|ˆ|‰|Š|‹|Œ|Ž|™|š|›|œ|ž|Ÿ)|ï»¿|ðŸ)")
    _CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    _FORMULA_COMMAND = re.compile(r"\\([A-Za-z]+)")
    _ALLOWED_FORMULA_COMMANDS = frozenset({
        "alpha", "beta", "gamma", "delta", "epsilon", "theta", "lambda",
        "mu", "pi", "rho", "sigma", "tau", "phi", "omega", "Gamma",
        "Delta", "Theta", "Lambda", "Pi", "Sigma", "Phi", "Omega",
        "frac", "sqrt", "sum", "prod", "int", "lim", "log", "ln", "exp",
        "sin", "cos", "tan", "min", "max", "argmin", "argmax", "left",
        "right", "cdot", "times", "div", "pm", "le", "leq", "ge", "geq",
        "ne", "approx", "in", "notin", "subset", "subseteq", "cup", "cap",
        "partial", "nabla", "infty", "mathrm", "mathbf", "mathit", "text",
        "begin", "end", "matrix", "pmatrix", "bmatrix", "cases", "quad",
    })

    def normalize(
        self,
        text: str,
        profile: TextProfile = TextProfile.PROSE,
        *,
        confidence: float | None = None,
        max_bytes: int | None = None,
    ) -> NormalizedText:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if "\ufffd" in text:
            raise TextDecodingError("text contains the Unicode replacement character")
        byte_budget = self.MAX_BYTES if max_bytes is None else max_bytes
        if not 1 <= byte_budget <= 50 * 1024 * 1024:
            raise ValueError("normalization byte budget is outside the safe range")
        if len(text.encode("utf-8")) > byte_budget:
            raise TextDecodingError("text exceeds the bounded normalization budget")
        original = text
        repaired = False
        warnings: list[str] = []
        before = self.anomaly_score(text)
        if profile in {TextProfile.PROSE, TextProfile.WEB, TextProfile.OCR}:
            candidate = self._repair_mojibake(text)
            if candidate != text and self.anomaly_score(candidate) < before:
                text, repaired = candidate, True
                warnings.append("mojibake repaired by a reversible round trip")
        if profile == TextProfile.FORMULA:
            self._validate_formula(text)
            normalized = unicodedata.normalize("NFC", text)
        elif profile in {TextProfile.PYTHON, TextProfile.NOTEBOOK}:
            # NFKC can change identifiers.  Python source therefore receives
            # only newline/BOM validation and NFC canonical composition.  The
            # same lossless rule applies to the notebook JSON container.
            normalized = unicodedata.normalize("NFC", text.removeprefix("\ufeff"))
            normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
            if self._CONTROL.search(normalized):
                raise TextDecodingError(
                    f"{profile.value} input contains forbidden control characters"
                )
        else:
            normalized = unicodedata.normalize("NFC", text.removeprefix("\ufeff"))
            normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
            normalized = self._CONTROL.sub("", normalized)
        return NormalizedText(
            text=normalized,
            encoding="unicode",
            profile=profile,
            repaired_mojibake=repaired,
            anomaly_score=self.anomaly_score(normalized),
            warnings=tuple(warnings),
            original=original if profile == TextProfile.OCR else "",
            confidence=confidence,
        )

    def decode_python(self, raw: bytes) -> NormalizedText:
        self._check_bytes(raw)
        try:
            encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
            text = raw.decode(encoding, errors="strict")
        except (LookupError, SyntaxError, UnicodeDecodeError) as exc:
            raise TextDecodingError(f"invalid declared Python encoding: {exc}") from exc
        result = self.normalize(text, TextProfile.PYTHON)
        return self._with_encoding(result, encoding)

    def decode_notebook(self, raw: bytes) -> NormalizedText:
        """Decode the JSON container strictly as UTF-8 or UTF-8 with BOM."""

        self._check_bytes(raw, max_bytes=50 * 1024 * 1024)
        encoding = "utf-8-sig" if raw.startswith(b"\xef\xbb\xbf") else "utf-8"
        try:
            text = raw.decode(encoding, errors="strict")
        except UnicodeDecodeError as exc:
            raise TextDecodingError("notebook is not valid UTF-8/UTF-8-SIG") from exc
        result = self.normalize(
            text, TextProfile.NOTEBOOK, max_bytes=50 * 1024 * 1024
        )
        return self._with_encoding(result, encoding)

    def decode_web(
        self,
        raw: bytes,
        *,
        headers: Mapping[str, str] | None = None,
        content_type: str = "",
    ) -> NormalizedText:
        self._check_bytes(raw)
        declared = self._http_charset(headers or {}, content_type)
        bom = self._bom_encoding(raw)
        meta = self._meta_encoding(raw[:16_384])
        candidates = tuple(dict.fromkeys(filter(None, (bom, declared, meta, "utf-8", "cp1252"))))
        decoded: list[tuple[str, str, int]] = []
        for encoding in candidates:
            try:
                value = raw.decode(encoding, errors="strict")
            except (LookupError, UnicodeDecodeError):
                continue
            decoded.append((encoding, value, self.anomaly_score(value)))
            if encoding in {bom, declared, meta} and self.anomaly_score(value) == 0:
                break
        if not decoded:
            raise TextDecodingError("Web response could not be decoded without data loss")
        # A declared encoding wins when valid; otherwise choose the least
        # anomalous reversible decoding with UTF-8 as deterministic tie-break.
        preferred = {name: rank for rank, name in enumerate((bom, declared, meta, "utf-8", "cp1252")) if name}
        encoding, text, _ = min(
            decoded,
            key=lambda item: (item[2], preferred.get(item[0], 99)),
        )
        result = self.normalize(unescape(text), TextProfile.WEB)
        return self._with_encoding(result, encoding)

    def normalize_ocr(self, text: str, *, confidence: float) -> NormalizedText:
        if not 0.0 <= confidence <= 1.0:
            raise ValueError("OCR confidence must be between 0 and 1")
        result = self.normalize(text, TextProfile.OCR, confidence=confidence)
        warnings = list(result.warnings)
        if confidence < 0.65:
            warnings.append("low OCR confidence; confirmation is required")
        return NormalizedText(
            text=result.text,
            encoding=result.encoding,
            profile=result.profile,
            repaired_mojibake=result.repaired_mojibake,
            anomaly_score=result.anomaly_score,
            warnings=tuple(warnings),
            original=result.original,
            confidence=confidence,
        )

    @classmethod
    def anomaly_score(cls, text: str) -> int:
        return (
            len(cls._MOJIBAKE.findall(text)) * 4
            + text.count("\ufffd") * 20
            + sum(1 for char in text if unicodedata.category(char) == "Cc" and char not in "\n\r\t")
        )

    @classmethod
    def _repair_mojibake(cls, text: str) -> str:
        if not cls._MOJIBAKE.search(text):
            return text

        def repair_piece(match: re.Match[str]) -> str:
            piece = match.group(0)
            for encoding in ("latin-1", "cp1252"):
                try:
                    candidate = piece.encode(encoding, errors="strict").decode(
                        "utf-8", errors="strict"
                    )
                    # Verify reversibility before accepting a repair.
                    if candidate.encode("utf-8").decode(encoding) == piece:
                        return candidate
                except (UnicodeEncodeError, UnicodeDecodeError):
                    continue
            return piece

        # Repair only suspicious runs.  Legitimate Unicode elsewhere (for
        # example an arrow or a mathematical symbol) must not make an otherwise
        # reversible repair fail.
        return cls._MOJIBAKE.sub(repair_piece, text)

    @classmethod
    def _validate_formula(cls, text: str) -> None:
        if len(text) > 8_000 or text.count("{") > 500:
            raise TextDecodingError("formula exceeds the safe rendering budget")
        if text.count("{") != text.count("}"):
            raise TextDecodingError("formula contains unbalanced braces")
        unknown = sorted(set(cls._FORMULA_COMMAND.findall(text)) - cls._ALLOWED_FORMULA_COMMANDS)
        if unknown:
            raise TextDecodingError(f"formula contains unsupported commands: {', '.join(unknown[:5])}")

    @staticmethod
    def _bom_encoding(raw: bytes) -> str | None:
        for marker, encoding in (
            (b"\xef\xbb\xbf", "utf-8-sig"),
            (b"\xff\xfe\x00\x00", "utf-32-le"),
            (b"\x00\x00\xfe\xff", "utf-32-be"),
            (b"\xff\xfe", "utf-16-le"),
            (b"\xfe\xff", "utf-16-be"),
        ):
            if raw.startswith(marker):
                return encoding
        return None

    @classmethod
    def _meta_encoding(cls, raw: bytes) -> str | None:
        match = cls._META_CHARSET.search(raw)
        if not match:
            return None
        value = next((group for group in match.groups() if group), b"")
        return value.decode("ascii", errors="ignore").casefold() or None

    @staticmethod
    def _http_charset(headers: Mapping[str, str], content_type: str) -> str | None:
        header = content_type or next(
            (value for key, value in headers.items() if key.casefold() == "content-type"),
            "",
        )
        match = re.search(r"charset\s*=\s*['\"]?\s*([\w.-]+)", header, re.IGNORECASE)
        return match.group(1).casefold() if match else None

    def _check_bytes(self, raw: bytes, *, max_bytes: int | None = None) -> None:
        if not isinstance(raw, bytes):
            raise TypeError("raw input must be bytes")
        budget = self.MAX_BYTES if max_bytes is None else max_bytes
        if len(raw) > budget:
            raise TextDecodingError("byte input exceeds the bounded decoding budget")

    @staticmethod
    def _with_encoding(result: NormalizedText, encoding: str) -> NormalizedText:
        return NormalizedText(
            text=result.text,
            encoding=encoding,
            profile=result.profile,
            repaired_mojibake=result.repaired_mojibake,
            anomaly_score=result.anomaly_score,
            warnings=result.warnings,
            original=result.original,
            confidence=result.confidence,
        )
