"""Run a bounded, reproducible local-service soak without private profile data."""

from __future__ import annotations

import argparse
import gc
import json
import sys
import tempfile
import threading
import time
import tracemalloc
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from aprendix.application.contracts import SearchRequestDTO  # noqa: E402
from aprendix.bootstrap import build_runtime  # noqa: E402


QUERIES = (
    "listas em Python",
    "programação orientada a objetos",
    "testes unitários pytest",
    "complexidade de algoritmos",
    "async await",
)


def _canonical_query(value: str) -> str:
    """Repair reversible source-literal mojibake in historical soak cases."""

    try:
        return value.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return value


def run(output: Path, *, cycles: int = 200) -> dict[str, object]:
    if not 1 <= cycles <= 5_000:
        raise ValueError("cycles must be between 1 and 5000")
    failures: list[str] = []
    durations: list[float] = []
    threads_before = threading.active_count()
    with tempfile.TemporaryDirectory(prefix="aprendix-soak-") as temporary:
        runtime = build_runtime(Path(temporary))
        tracemalloc.start()
        gc.collect()
        retained_before, _ = tracemalloc.get_traced_memory()
        started = time.perf_counter()
        for index in range(cycles):
            operation_started = time.perf_counter()
            try:
                result = runtime.search_service.search(
                    SearchRequestDTO(query=_canonical_query(QUERIES[index % len(QUERIES)]))
                )
                if not result.evidence:
                    failures.append(f"empty-search:{index}")
                if not runtime.curriculum.glossary("else", limit=3):
                    failures.append(f"empty-dictionary:{index}")
                if index % 10 == 0 and runtime.platform.health(deep=False).status.value != "healthy":
                    failures.append(f"health:{index}")
            except Exception as exc:  # report the failure; never hide it
                failures.append(f"{index}:{type(exc).__name__}")
            durations.append((time.perf_counter() - operation_started) * 1000)
        elapsed = time.perf_counter() - started
        gc.collect()
        retained_after, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        with runtime.database.read_connection() as connection:
            integrity = str(connection.execute("PRAGMA integrity_check").fetchone()[0])
    threads_after = threading.active_count()
    ordered = sorted(durations)
    p95 = ordered[min(len(ordered) - 1, max(0, round(len(ordered) * 0.95 - 1)))]
    report: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "profile": "fresh-temporary-no-user-data",
        "cycles": cycles,
        "elapsed_seconds": round(elapsed, 3),
        "operations_per_second": round(cycles / max(elapsed, 0.001), 3),
        "cycle_p95_ms": round(p95, 3),
        "retained_growth_bytes": max(0, retained_after - retained_before),
        "peak_traced_bytes": peak,
        "thread_delta": threads_after - threads_before,
        "database_integrity": integrity,
        "failure_count": len(failures),
        "failure_codes": failures[:20],
        "limits": {
            "retained_growth_bytes": 32 * 1024 * 1024,
            "peak_traced_bytes": 256 * 1024 * 1024,
            "thread_delta": 1,
        },
    }
    report["passed"] = bool(
        not failures
        and integrity == "ok"
        and report["retained_growth_bytes"] <= report["limits"]["retained_growth_bytes"]
        and peak <= report["limits"]["peak_traced_bytes"]
        and report["thread_delta"] <= report["limits"]["thread_delta"]
    )
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("SOAK-BENCHMARK-1.0.0.json"))
    parser.add_argument("--cycles", type=int, default=200)
    arguments = parser.parse_args()
    measured = run(arguments.output.resolve(), cycles=arguments.cycles)
    print(json.dumps(measured, indent=2, ensure_ascii=False))
    raise SystemExit(0 if measured["passed"] else 1)
