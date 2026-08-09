"""Build a privacy-safe bibliography catalogue from user-approved PDF folders.

Only bibliographic metadata, page counts and relative locators are retained.
No book body, exercise statement or extracted page text is copied into Aprendix.
The resulting JSON is deterministic and can be bundled as an offline source map.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT / "src" / "aprendix" / "presentation" / "assets"
    / "local-library-catalog.json"
)

TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("python-foundations", ("python", "programming", "programacao", "algoritmia")),
    ("object-oriented-python", ("object oriented", "object-oriented", "poo", "oop")),
    ("classic-algorithms", ("algorithm", "algoritmo", "aed", "data structure")),
    ("data-structures", ("data structure", "stack", "queue", "tree", "graph theory")),
    ("databases", ("database", "sql", "nosql", "mongodb")),
    ("classical-ml", ("machine learning", "pattern recognition", "supervised")),
    ("unsupervised-learning", ("unsupervised", "cluster", "clustering", "pca")),
    ("deep-learning", ("deep learning", "neural", "keras", "pytorch")),
    ("reinforcement-learning", ("reinforcement", "rl ", "q-learning")),
    ("autonomous-agents", ("agent", "multiagent", "multi-agent")),
    ("computer-vision", ("computer vision", "image", "segmentation")),
    ("web", ("web", "html", "css", "javascript", "react", "flask", "django")),
    ("mathematics", ("mathematics", "calculus", "algebra", "probability", "statistics")),
    ("software-engineering", ("software", "testing", "design", "architecture")),
)


def _fold(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = value.encode("ascii", "ignore").decode().casefold()
    return re.sub(r"\s+", " ", value).strip()


def _clean_title(path: Path, metadata_title: str) -> str:
    title = metadata_title.strip() if metadata_title else path.stem
    title = re.sub(r"\s+--\s+.*$", "", title)
    title = re.sub(r"\s+", " ", title).strip(" ._-")
    return title or path.stem


def _authors(raw: str | None) -> tuple[str, ...]:
    if not raw:
        return ()
    parts = re.split(r"\s*(?:;|\band\b|&|\|)\s*", raw, flags=re.IGNORECASE)
    return tuple(dict.fromkeys(item.strip() for item in parts if item.strip()))[:12]


def _topics(path: Path, title: str) -> tuple[str, ...]:
    haystack = _fold(f"{path.parent.as_posix()} {title}")
    found = [topic for topic, keywords in TOPIC_RULES if any(key in haystack for key in keywords)]
    return tuple(found or ("software-engineering",))


def _identity(title: str, authors: tuple[str, ...]) -> str:
    canonical = _fold(title) + "|" + "|".join(_fold(author) for author in authors)
    return "local-" + hashlib.sha256(canonical.encode()).hexdigest()[:20]


def catalogue(roots: tuple[tuple[str, Path], ...]) -> dict[str, object]:
    grouped: dict[str, dict[str, object]] = {}
    errors: list[dict[str, str]] = []
    for root_key, root in roots:
        for path in sorted(root.rglob("*.pdf"), key=lambda item: _fold(str(item))):
            if "bookslazer" in {_fold(part) for part in path.parts}:
                continue
            try:
                reader = PdfReader(path, strict=False)
                metadata = reader.metadata or {}
                raw_title = str(metadata.get("/Title") or "")
                title = _clean_title(path, raw_title)
                authors = _authors(str(metadata.get("/Author") or ""))
                identity = _identity(title, authors)
                locator = {
                    "root": root_key,
                    "relative_path": path.relative_to(root).as_posix(),
                    "size_bytes": path.stat().st_size,
                }
                if identity not in grouped:
                    grouped[identity] = {
                        "id": identity,
                        "title": title,
                        "authors": authors,
                        "page_count": len(reader.pages),
                        "source_type": "book-or-paper",
                        "topics": _topics(path, title),
                        "provenance": "user-approved-local-library",
                        "usage": "bibliographic-orientation-only",
                        "locators": [],
                    }
                grouped[identity]["locators"].append(locator)
            except Exception as exc:  # malformed/encrypted PDFs stay quarantined
                errors.append({
                    "root": root_key,
                    "relative_path": path.relative_to(root).as_posix(),
                    "error": type(exc).__name__,
                })
    items = sorted(grouped.values(), key=lambda item: (_fold(str(item["title"])), str(item["id"])))
    topic_counts: dict[str, int] = defaultdict(int)
    for item in items:
        item["authors"] = list(item["authors"])
        item["topics"] = list(item["topics"])
        item["locators"] = sorted(item["locators"], key=lambda value: (value["root"], value["relative_path"]))
        for topic in item["topics"]:
            topic_counts[topic] += 1
    return {
        "schema_version": 1,
        "policy": {
            "contains_absolute_paths": False,
            "contains_book_body": False,
            "content_may_be_copied": False,
            "purpose": "source provenance and thematic coverage",
        },
        "root_keys": [key for key, _path in roots],
        "source_count": len(items),
        "topic_counts": dict(sorted(topic_counts.items())),
        "sources": items,
        "quarantined": sorted(errors, key=lambda item: (item["root"], item["relative_path"])),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", action="append", nargs=2, metavar=("KEY", "PATH"), required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    roots = tuple((key, Path(path).expanduser().resolve()) for key, path in args.root)
    missing = [str(path) for _key, path in roots if not path.is_dir()]
    if missing:
        raise FileNotFoundError("Pastas em falta: " + ", ".join(missing))
    result = catalogue(roots)
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{output} | fontes={result['source_count']} | quarentena={len(result['quarantined'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
