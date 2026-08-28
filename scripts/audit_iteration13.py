"""End-to-end, aggregate-only release audit for Iteration 13."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
for candidate in (ROOT / "src", ROOT / "mobile"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from aprendix.application.contracts import (  # noqa: E402
    SearchRequestDTO, SnippetAction, SnippetRequestDTO, TutorRequestDTO,
)
from aprendix.bootstrap import build_runtime  # noqa: E402
from aprendix.application.editor_support import diagnose_python  # noqa: E402
from aprendix.presentation.responsive import responsive_matrix  # noqa: E402
from aprendix_mobile.paths import PlatformPaths  # noqa: E402
from aprendix_mobile.runtime import build_mobile_runtime  # noqa: E402


def audit(data_directory: Path) -> dict[str, object]:
    started = time.perf_counter()
    runtime = build_runtime(data_directory / "desktop")
    journeys: dict[str, dict[str, object]] = {}

    def check(name: str, operation) -> object:
        step_started = time.perf_counter()
        try:
            value, detail = operation()
            passed, error = bool(value), ""
        except Exception as exc:  # the report must preserve every independent gate
            passed, detail, error = False, "gate raised an exception", type(exc).__name__
        journeys[name] = {
            "passed": passed, "detail": detail,
            "duration_ms": round((time.perf_counter() - step_started) * 1_000, 2),
            "error_type": error,
        }
        return passed

    check("database", lambda: (
        runtime.platform.health().status.value == "healthy",
        f"schema {runtime.platform.health().schema_version}",
    ))
    check("curriculum", lambda: (
        runtime.curriculum.audit()["valid"],
        f"{len(runtime.curriculum.tracks())} tracks",
    ))
    check("ide_sandbox", lambda: (
        runtime.desktop.run("print(sum(range(5)))").stdout.strip() == "10",
        "isolated execution and output",
    ))
    check("ide_diagnostics", lambda: (
        bool(diagnose_python("if True:\n\t print('x')\n")),
        "static diagnostics returned",
    ))
    check("hybrid_search", lambda: (
        bool((response := runtime.search_service.search(SearchRequestDTO(
            query="funções Python", allow_web_fallback=False, max_results=5,
        ))).evidence),
        f"{len(response.evidence)} evidence items",
    ))
    check("dictionary", lambda: (
        bool((items := runtime.curriculum.glossary("else", limit=5))),
        f"{len(items)} local matches",
    ))
    check("curiosity_cards", lambda: (
        bool((cards := runtime.knowledge.list_theory_cards(limit=12, authored_only=True)))
        and all(item.source_title and item.graph_node_id for item in cards),
        f"{len(cards)} sourced graph-linked cards sampled",
    ))
    check("knowledge_graph", lambda: (
        bool((snapshot := runtime.graph_snapshot_service.get_snapshot(runtime.user.id)).nodes)
        and bool(snapshot.recommendations),
        f"{len(snapshot.nodes)} nodes; {len(snapshot.recommendations)} recommendations",
    ))
    check("offline_tutor", lambda: (
        not (answer := runtime.tutor.answer(TutorRequestDTO(
            question="Como funciona o operador módulo em Python?"
        ))).declined and bool(answer.evidence),
        f"{len(answer.evidence)} grounded evidence items",
    ))
    check("snippet_assistant", lambda: (
        (analysis := runtime.snippets.analyze(SnippetRequestDTO(
            text="def dobro(x):\n    return x * 2", action=SnippetAction.CREATE_TESTS,
        ))).detected_language == "python" and bool(analysis.suggested_tests),
        f"{len(analysis.suggested_tests)} suggested tests",
    ))
    check("games_isolation", lambda: (
        (session := runtime.games.new("sudoku", "Fácil")).game is not None,
        f"local session {session.game.name if hasattr(session.game, 'name') else 'sudoku'}",
    ))
    check("pedagogical_compiler", lambda: (
        (quality := runtime.quality.summary()) is not None
        and quality.total > 4_000 and quality.quarantined == 0,
        (f"{quality.total} compiled; {quality.quarantined} quarantined"
         if quality is not None else "no audit"),
    ))
    check("adaptive_progress", lambda: (
        (forecast := runtime.progress.forecast(runtime.user.id)).remaining_nodes >= 0
        and ((report := runtime.progress.weekly_report(runtime.user.id)).week_end
             - report.week_start).days == 6,
        f"confidence {forecast.confidence:.2f}; weekly report 7 days",
    ))
    check("bibliography", lambda: (
        (coverage := runtime.content.bibliography_coverage()).objective_count > 0
        and coverage.covered_objectives == coverage.objective_count,
        f"{coverage.covered_objectives}/{coverage.objective_count} objectives covered",
    ))
    matrix = responsive_matrix()
    check("responsive_layout", lambda: (
        bool(matrix["passed"]), f"{len(matrix['profiles'])} release viewports",
    ))

    mobile_paths = PlatformPaths.resolve(
        user_data_dir=data_directory / "mobile" / "data",
        cache_dir=data_directory / "mobile" / "cache",
        resources_dir=ROOT / "mobile" / "assets",
    )
    mobile = build_mobile_runtime(mobile_paths, allow_host_development=True)
    check("mobile_parity", lambda: (
        bool(mobile.cards()) and bool(mobile.courses())
        and mobile.progress_report()["total_units"] > 0,
        (f"{len(mobile.cards())} cards; {len(mobile.courses())} courses; "
         f"{mobile.progress_report()['total_units']} units"),
    ))

    passed = all(item["passed"] for item in journeys.values())
    return {
        "audit_version": "iteration-13.1",
        "passed": passed,
        "privacy": {
            "aggregate_only": True, "contains_user_content": False,
            "contains_user_identifiers": False, "contains_paths": False,
        },
        "journeys": journeys,
        "manual_release_gates": {
            "windows_mixed_dpi": "requires-two-physical-monitors",
            "android_touch": "requires-physical-device",
            "ios_build_and_touch": "requires-macos-xcode-and-physical-device",
            "authenticode": "requires-publisher-certificate",
        },
        "duration_ms": round((time.perf_counter() - started) * 1_000, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Aprendix Iteration 13")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--output", type=Path, default=REPORTS / "ITERATION-13-AUDIT-1.0.0.json")
    args = parser.parse_args()
    if args.data_dir:
        report = audit(args.data_dir.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="aprendix-iteration13-") as temporary:
            report = audit(Path(temporary))
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", "utf-8")
    print(output)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
