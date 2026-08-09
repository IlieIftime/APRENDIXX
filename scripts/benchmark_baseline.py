"""Produce a privacy-safe, reproducible Aprendix runtime baseline report."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from aprendix.application.contracts import SearchRequestDTO  # noqa: E402
from aprendix.bootstrap import build_runtime  # noqa: E402


def _measure(operation, iterations: int) -> tuple[list[float], object]:
    values: list[float] = []
    result = None
    for _ in range(iterations):
        started = time.perf_counter()
        result = operation()
        values.append((time.perf_counter() - started) * 1000)
    return values, result


def _summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    p95_index = min(len(ordered) - 1, max(0, round(0.95 * len(ordered) - 1)))
    return {
        "min_ms": round(min(values), 3),
        "median_ms": round(statistics.median(values), 3),
        "p95_ms": round(ordered[p95_index], 3),
        "max_ms": round(max(values), 3),
    }


def benchmark(data_directory: Path, *, iterations: int) -> dict[str, object]:
    started = time.perf_counter()
    runtime = build_runtime(data_directory)
    startup_ms = (time.perf_counter() - started) * 1000
    search_times, search = _measure(
        lambda: runtime.search_service.search(SearchRequestDTO(query="listas em Python")),
        iterations,
    )
    dictionary_times, dictionary = _measure(
        lambda: runtime.curriculum.glossary("else", limit=8), iterations,
    )
    sandbox_times, sandbox = _measure(
        lambda: runtime.desktop.run("print(sum([1, 2, 3]))"), max(1, min(iterations, 3)),
    )
    health_times, health = _measure(lambda: runtime.platform.health(deep=False), iterations)
    with runtime.database.read_connection() as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        counts = {
            table: int(connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0])
            for table in ("exercises", "document_chunks", "theory_cards", "glossary_entries")
        }
    return {
        "schema_version": health.schema_version,
        "startup_ms": round(startup_ms, 3),
        "operations": {
            "search": {**_summary(search_times), "result_count": len(search.evidence)},
            "dictionary": {**_summary(dictionary_times), "result_count": len(dictionary)},
            "sandbox": {**_summary(sandbox_times), "status": sandbox.status},
            "health": {**_summary(health_times), "status": health.status.value},
        },
        "database": {"integrity": integrity, **counts},
        "privacy": {
            "contains_queries": False,
            "contains_source_code": False,
            "contains_user_paths": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--iterations", type=int, default=5)
    args = parser.parse_args()
    if not 1 <= args.iterations <= 100:
        parser.error("--iterations must be between 1 and 100")
    if args.data_dir:
        report = benchmark(args.data_dir.resolve(), iterations=args.iterations)
    else:
        with tempfile.TemporaryDirectory(prefix="aprendix-baseline-") as temporary:
            report = benchmark(Path(temporary), iterations=args.iterations)
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        output = args.output.resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8")
        print(output)
    else:
        print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
