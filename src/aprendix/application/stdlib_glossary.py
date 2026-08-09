"""Load the generated, metadata-only Python standard-library glossary."""

from __future__ import annotations

import json
from pathlib import Path


def _load() -> tuple[dict[str, object], ...]:
    asset = Path(__file__).resolve().parents[1] / "presentation" / "assets" / "stdlib-glossary.json"
    try:
        payload = json.loads(asset.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return ()
    return tuple(payload.get("entries", ()))


STDLIB_GLOSSARY = _load()
