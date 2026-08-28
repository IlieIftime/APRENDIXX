"""Acceptance gate for the governed desktop bibliography catalogue."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from aprendix.application.knowledge_structure import (
    LOCAL_LIBRARY_SOURCES,
    OFFICIAL_PYTHON_API_SOURCES,
    SOURCES,
)
from aprendix.bootstrap import build_runtime


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "ITERATION-16-AUDIT-1.0.0.json"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aprendix-iteration16-") as directory:
        runtime = build_runtime(Path(directory))
        coverage = runtime.content.bibliography_coverage()
        with runtime.database.read_connection() as connection:
            stored = int(connection.execute(
                "SELECT count(*) FROM curated_sources"
            ).fetchone()[0])
        checks = {
            "aaa_catalogue_target": stored >= 1_000,
            "unique_ids_and_urls": (
                len({source.id for source in SOURCES}) == len(SOURCES)
                and len({source.url for source in SOURCES}) == len(SOURCES)
            ),
            "official_docs_allowlisted": all(
                source.source_type == "documentation"
                and source.authors == ("Python Software Foundation",)
                and source.url.startswith("https://docs.python.org/3/library/")
                and "#" in source.url
                for source in OFFICIAL_PYTHON_API_SOURCES
            ),
            "local_library_is_metadata_only": all(
                source.url.startswith("aprendix-library://")
                and source.provenance == "user-approved-local-library-metadata-2026-08"
                for source in LOCAL_LIBRARY_SOURCES
            ),
            "every_objective_has_three_sources": (
                coverage.objective_count > 0
                and coverage.triple_sourced_objectives == coverage.objective_count
                and not coverage.weak_objective_codes
            ),
        }
        report = {
            "iteration": 16,
            "passed": all(checks.values()),
            "checks": checks,
            "metrics": {
                "stored_sources": stored,
                "official_python_api_entries": len(OFFICIAL_PYTHON_API_SOURCES),
                "local_library_entries": len(LOCAL_LIBRARY_SOURCES),
                "objectives": coverage.objective_count,
                "triple_sourced_objectives": coverage.triple_sourced_objectives,
                "bibliography_coverage_score": coverage.coverage_score,
            },
            "privacy": "metadata and aggregate coverage only; no local absolute paths or text",
        }
        OUTPUT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
