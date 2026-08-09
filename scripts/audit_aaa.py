"""Audit measurable Aprendix AAA gates without inspecting private user data.

By default the audit creates a fresh temporary profile.  ``--data-dir`` may be
used deliberately to audit another profile, but the report contains aggregate
counts only: no source text, answers, code, paths or user identifiers.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from aprendix.bootstrap import build_runtime  # noqa: E402


CURRICULUM_TARGETS: dict[str, tuple[int, int | None]] = {
    "learning_tracks": (12, None),
    "learning_units": (150, 250),
    "graph_nodes": (2_000, None),
    "exercises": (3_000, None),
    "authored_cards": (1_000, None),
    "glossary_entries": (5_000, None),
    "curated_sources": (1_000, None),
}


def _count(connection, table: str) -> int:
    return int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


def _within(value: int, minimum: int, maximum: int | None) -> bool:
    return value >= minimum and (maximum is None or value <= maximum)


def audit(data_directory: Path) -> dict[str, object]:
    runtime = build_runtime(data_directory)
    # Coverage is derived data and must be refreshed before measuring it.
    runtime.content.refresh_objective_evidence()
    runtime.content.refresh_coverage()
    with runtime.database.read_connection() as connection:
        counts = {
            table: _count(connection, table)
            for table in (
                "learning_tracks",
                "learning_units",
                "curriculum_objectives",
                "graph_nodes",
                "exercises",
                "glossary_entries",
                "curated_sources",
                "bibliography_links",
                "guided_project_templates",
                "content_source_adapters",
            )
        }
        counts["glossary_aliases"] = _count(connection, "glossary_aliases")
        counts["authored_cards"] = int(connection.execute(
            """SELECT count(*) FROM theory_cards c
               JOIN document_chunks ch ON ch.id=c.chunk_id
               JOIN documents d ON d.id=ch.document_id
               WHERE d.source_path='aprendix://authored-facts/v1'"""
        ).fetchone()[0])
        coverage = {
            row["gap_code"]: int(row["amount"])
            for row in connection.execute(
                "SELECT gap_code,count(*) amount FROM curriculum_coverage GROUP BY gap_code"
            ).fetchall()
        }
        orphan_units = int(connection.execute(
            """SELECT count(*) FROM learning_units u
               LEFT JOIN learning_chapters c ON c.id=u.chapter_id
               WHERE c.id IS NULL"""
        ).fetchone()[0])
        practice_without_exercise = int(connection.execute(
            "SELECT count(*) FROM learning_units WHERE kind='practice' AND exercise_id IS NULL"
        ).fetchone()[0])
        integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])

    target_results = {}
    for name, (minimum, maximum) in CURRICULUM_TARGETS.items():
        actual = int(counts[name]) + (
            int(counts["glossary_aliases"]) if name == "glossary_entries" else 0
        )
        target_results[name] = {
            "actual": actual,
            "minimum": minimum,
            "maximum": maximum,
            "passed": _within(actual, minimum, maximum),
        }
    curriculum_gate = (
        all(item["passed"] for item in target_results.values())
        and sum(amount for gap, amount in coverage.items() if gap != "none") == 0
        and orphan_units == 0
        and practice_without_exercise == 0
        and integrity == "ok"
    )
    return {
        "audit_version": "1",
        "privacy": {
            "aggregate_only": True,
            "contains_user_content": False,
            "contains_user_identifiers": False,
            "contains_paths": False,
        },
        "database": {"integrity": integrity, "schema_version": runtime.platform.health().schema_version},
        "counts": counts,
        "curriculum": {
            "status": "passed" if curriculum_gate else "open",
            "targets": target_results,
            "coverage_by_gap": coverage,
            "orphan_units": orphan_units,
            "practice_without_exercise": practice_without_exercise,
        },
        "external_gates": {
            "android_physical": "not-measured-by-this-host",
            "ios_build_and_physical": "not-measured-by-this-host",
            "authenticode": "requires-publisher-certificate",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit measurable Aprendix AAA gates")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.data_dir:
        report = audit(args.data_dir.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="aprendix-aaa-audit-") as temporary:
            report = audit(Path(temporary))
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
        print(output)
    else:
        print(encoded, end="")
    return 0 if report["database"]["integrity"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
