"""Resolve privacy-safe locators for the optional user-approved PDF library."""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import unquote, urlparse


LIBRARY_SCHEME = "aprendix-library"


def candidate_roots(root_key: str) -> tuple[Path, ...]:
    environment_key = "APRENDIX_LIBRARY_" + root_key.upper().replace("-", "_")
    configured = os.environ.get(environment_key, "").strip()
    home = Path.home()
    if root_key == "estudo-ferias":
        relative = Path("treino prog") / "estudo ferias"
    elif root_key == "ebooks-papers":
        relative = Path("ebooks e pappers")
    else:
        return (Path(configured).expanduser(),) if configured else ()
    candidates = []
    if configured:
        candidates.append(Path(configured).expanduser())
    candidates.extend((
        home / "OneDrive" / "Ambiente de Trabalho" / relative,
        home / "Desktop" / relative,
        home / "Ambiente de Trabalho" / relative,
    ))
    return tuple(dict.fromkeys(path.resolve() for path in candidates))


def resolve_library_uri(value: str) -> Path | None:
    parsed = urlparse(value)
    if parsed.scheme != LIBRARY_SCHEME or not parsed.netloc:
        return None
    relative = Path(unquote(parsed.path.lstrip("/")))
    if relative.is_absolute() or ".." in relative.parts:
        return None
    for root in candidate_roots(parsed.netloc):
        candidate = (root / relative).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            continue
        if candidate.is_file():
            return candidate
    return None
