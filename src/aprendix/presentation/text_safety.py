"""Last-mile Unicode hygiene for labels fed by OCR, Web, and legacy data."""

from __future__ import annotations

import re
import unicodedata

_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MOJIBAKE_MARKERS = (
    "Ã", "Â", "â", "ð", "Î", "Ï", "ï»¿",
    "â€", "â€™", "â€œ", "â€“", "â€”",
)


def _mojibake_score(value: str) -> int:
    return sum(value.count(marker) for marker in _MOJIBAKE_MARKERS)


def normalize_ui_text(value: object) -> str:
    """Return NFC text and repair only an unambiguous UTF-8/Latin-1 mix-up.

    Code editors deliberately do not call this function: normalization is for
    human-facing copy only, never source code or user input semantics.
    """

    text = str(value or "").replace("\ufeff", "").replace("\ufffd", "")
    # Two bounded rounds also repair legacy content that was accidentally
    # decoded twice, while correctly encoded words such as "âmbito" remain
    # unchanged because neither legacy round forms valid UTF-8.
    for _round in range(2):
        if not _mojibake_score(text):
            break
        candidates = [text]
        for legacy_encoding in ("cp1252", "latin-1"):
            try:
                candidates.append(text.encode(legacy_encoding).decode("utf-8"))
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
        repaired = min(
            candidates,
            key=lambda candidate: (_mojibake_score(candidate), len(candidate)),
        )
        if repaired == text:
            break
        text = repaired
    text = _CONTROL_RE.sub("", text)
    return unicodedata.normalize("NFC", text)
