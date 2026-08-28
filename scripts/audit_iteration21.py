"""Reproducible, aggregate-only acceptance audit for desktop Iteration 21.

The auditor builds a disposable profile and exercises production repositories
and services.  It emits counts and pass/fail evidence only: no learner text,
identifiers, encryption keys or absolute paths are written to the report.
Physical display, assistive-technology and signed-installer checks deliberately
remain external release gates.
"""

from __future__ import annotations

import argparse
import builtins
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from aprendix.application.contracts import SnippetAction, SnippetRequestDTO
from aprendix.application.editorial_catalog import EDITORIAL_EXERCISES
from aprendix.application.math_rendering import FormulaRenderRequest
from aprendix.application.search_holdout import CatalogSearchBenchmark
from aprendix.application.snippet_analysis import SnippetAnalyzer
from aprendix.application.text_normalization import (
    TextDecodingError,
    TextNormalizationService,
    TextProfile,
)
from aprendix.bootstrap import build_runtime
from aprendix.infrastructure.grading import IsolatedGradingExecutor, OopGradingPolicy
from aprendix.presentation.math_renderer import OfflineMathRenderer
from aprendix.presentation.responsive import book_workspace_profile

OUTPUT = ROOT / "reports" / "ITERATION-21-AUDIT-1.0.0.json"
_SOURCE_FIRST_QUERIES = (
    "capital acumulado juros compostos",
    "decoradores Python",
    "backpropagation regra da cadeia",
)
_FORMULAS = (
    r"\frac{x+1}{2}", r"x^{n+1}", r"\sum_{i=1}^{n}x_i",
    r"\sqrt{x^2+y^2}", r"\begin{matrix}a&b\\c&d\end{matrix}",
    r"\alpha + \beta \le \gamma",
)


def _golden_snippets() -> tuple[str, ...]:
    templates = (
        "def total_{n}(values):\n    total = 0\n    for value in values:\n        total += value\n    return total",
        "def choose_{n}(value):\n    if value > {n}:\n        return value\n    return {n}",
        "class Meter{n}:\n    def __init__(self, value):\n        self.value = value\n    def read(self):\n        return self.value",
        "def outer_{n}(x):\n    def inner(y):\n        return x + y\n    return inner({n})",
        "def lookup_{n}(items, target):\n    for index, item in enumerate(items):\n        if item == target:\n            return index\n    return -1",
        "def mapping_{n}(items):\n    return {{item: len(item) for item in items}}",
        "def guarded_{n}(value):\n    try:\n        return 10 / value\n    except ZeroDivisionError:\n        return 0",
        "def unreachable_{n}(flag):\n    return flag\n    flag = {n}",
        "import math\ndef distance_{n}(x, y):\n    return math.sqrt(x*x + y*y)",
        "def shadow_{n}(list):\n    result = []\n    while list:\n        result.append(list.pop())\n    return result",
    )
    return tuple(template.format(n=index) for template in templates for index in range(5))


def audit(data_directory: Path) -> dict[str, object]:
    """Run every independent Iteration-21 gate against a disposable profile."""

    started = time.perf_counter()
    runtime = build_runtime(data_directory)
    checks: dict[str, dict[str, object]] = {}
    metrics: dict[str, object] = {}

    def check(name: str, operation) -> bool:
        gate_started = time.perf_counter()
        try:
            passed, detail = operation()
            error_type = ""
        except Exception as exc:  # noqa: BLE001 - independent gates must survive
            passed, detail, error_type = False, "gate raised an exception", type(exc).__name__
        checks[name] = {
            "passed": bool(passed), "detail": str(detail),
            "duration_ms": round((time.perf_counter() - gate_started) * 1_000, 2),
            "error_type": error_type,
        }
        return bool(passed)

    health = runtime.platform.health()
    with runtime.database.read_connection() as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = len(connection.execute("PRAGMA foreign_key_check").fetchall())
    metrics["schema_version"] = health.schema_version
    check("schema_38_integrity", lambda: (
        health.schema_version == 38 and integrity == "ok" and foreign_keys == 0,
        f"schema={health.schema_version}; integrity={integrity}; foreign_keys={foreign_keys}",
    ))

    catalog = runtime.catalog.audit()
    catalog_counts = catalog.get("counts", {})
    delta = catalog_counts.get("delta", {}) if isinstance(catalog_counts, dict) else {}
    with runtime.database.read_connection() as connection:
        archived_legacy_cards = int(connection.execute(
            """SELECT count(*) FROM content_catalog_items i
               JOIN content_catalog_releases r ON r.id=i.release_id
               WHERE r.status='active' AND i.item_type='card'
                 AND i.status='archived' AND i.content_type='imported'"""
        ).fetchone()[0])
        active_editorial_cards = int(connection.execute(
            """SELECT count(*) FROM content_catalog_items i
               JOIN content_catalog_releases r ON r.id=i.release_id
               WHERE r.status='active' AND i.item_type='card' AND i.status='active'"""
        ).fetchone()[0])
        indexed_cards = int(connection.execute(
            "SELECT count(*) FROM catalog_search_entries WHERE entity_type='card'"
        ).fetchone()[0])
        authored_card_aggregate_readings = int(connection.execute(
            """SELECT count(*) FROM catalog_search_entries e
               JOIN documents d ON d.id=e.entity_id
               WHERE e.entity_type='reading'
                 AND d.source_path='aprendix://authored-facts/v1'"""
        ).fetchone()[0])
    metrics.update({
        "catalog_counts": catalog_counts,
        "catalog_delta": delta,
        "catalog_quality": {
            key: catalog.get(key)
            for key in (
                "duplicate_source_keys", "empty_source_keys", "bad_sources",
                "official_source_families", "card_source_minimum",
                "glossary_source_minimum", "glossary_example_minimum",
                "exercise_diversity",
            )
        },
        "archived_cards_visible": catalog.get("archived_cards_visible", -1),
        "archived_legacy_cards": archived_legacy_cards,
        "indexed_editorial_cards": indexed_cards,
        "authored_card_aggregate_readings": authored_card_aggregate_readings,
    })
    check("catalog_release_and_exact_minimum_deltas", lambda: (
        bool(catalog.get("passed"))
        and all(int(delta.get(kind, 0)) == minimum for kind, minimum in {
            "source": 500, "card": 1_000, "glossary": 1_000,
            "exercise": 500, "project": 50,
        }.items()),
        "active governed release; additive approved deltas meet Iteration-21 targets",
    ))
    check("legacy_cards_are_excluded_not_deleted", lambda: (
        int(catalog.get("archived_cards_visible", -1)) == 0
        and indexed_cards == active_editorial_cards == int(catalog_counts.get("card", -1))
        and authored_card_aggregate_readings == 0,
        (
            f"visible archived cards={catalog.get('archived_cards_visible')}; "
            f"indexed/active cards={indexed_cards}/{active_editorial_cards}; "
            f"preserved legacy records={archived_legacy_cards}; aggregate readings=0"
        ),
    ))

    career = catalog.get("career", {})
    generated = catalog.get("generated_exercises", {})
    metrics["career"] = career
    metrics["career_dag_cycles"] = catalog.get("dag_cycles", -1)
    check("five_career_dags_and_projects", lambda: (
        int(career.get("roles", 0)) == 5
        and int(career.get("nodes", 0)) > 0
        and int(career.get("track_links", 0)) >= int(career.get("nodes", 0))
        and int(career.get("project_links", 0)) == 50
        and int(catalog.get("dag_cycles", -1)) == 0,
        (
            f"roles={career.get('roles')}; nodes={career.get('nodes')}; "
            f"project links={career.get('project_links')}; cycles={catalog.get('dag_cycles')}"
        ),
    ))
    check("exercise_solution_policy_provenance", lambda: (
        int(generated.get("total", 0)) == 500
        and all(int(generated.get(key, -1)) == 0 for key in (
            "missing_source", "missing_solution", "missing_policy",
        )),
        f"500 exercises; missing source/solution/policy={tuple(generated.get(k) for k in ('missing_source','missing_solution','missing_policy'))}",
    ))

    policy = OopGradingPolicy()
    executor = IsolatedGradingExecutor()
    solution_passes = 0
    for exercise in EDITORIAL_EXERCISES:
        tests = "\n".join(exercise.tests)
        if not policy.violations(exercise.solution) and not policy.violations(tests, trusted_test=True):
            status, _message = executor.run_test(exercise.solution, tests, timeout_ms=2_000)
            solution_passes += status == "passed"
    metrics["sandbox_validated_reference_solutions"] = solution_passes
    check("all_reference_solutions_pass_in_sandbox", lambda: (
        solution_passes == len(EDITORIAL_EXERCISES) == 500,
        f"{solution_passes}/{len(EDITORIAL_EXERCISES)} trusted solutions passed isolated tests",
    ))

    capital = next(item for item in EDITORIAL_EXERCISES if item.slug == "career-capital-acumulado")
    capital_policy = runtime.catalog.guidance_policy(next(
        item.id for item in runtime.exercises.list_all() if item.slug == capital.slug
    ))
    check("capital_accumulation_acceptance_case", lambda: (
        "1530.00, 1537.50, 1545.00" in capital.prompt
        and "2023 -> 1591.81, 1615.34, 1639.09" in capital.prompt
        and "capital_inicial * (1 + t / 100) ** n" in capital.prompt
        and bool(capital_policy and capital_policy.get("expected_trace"))
        and int(capital_policy.get("failed_attempts_before_solution", 0)) >= 4,
        "canonical formula/table/trace and progressive reveal policy are present",
    ))

    search = CatalogSearchBenchmark(runtime.pedagogy).run()
    metrics.update({
        "search_holdout_version": search.algorithm_version,
        "search_holdout_queries": search.query_count,
        "search_recall_at_10": round(search.recall_at_10, 6),
        "search_mrr": round(search.mrr, 6),
        "search_ndcg_at_10": round(search.ndcg_at_10, 6),
        "search_hard_negative_rate_at_3": round(search.hard_negative_rate_at_3, 6),
        "search_p95_ms": round(search.p95_ms, 3),
    })
    check("source_first_search_holdout_v3", lambda: (
        search.query_count >= 250 and search.passed,
        (
            f"queries={search.query_count}; Recall@10={search.recall_at_10:.3f}; "
            f"nDCG@10={search.ndcg_at_10:.3f}; hard-neg@3={search.hard_negative_rate_at_3:.3f}; "
            f"P95={search.p95_ms:.2f} ms"
        ),
    ))
    regression_tops: dict[str, tuple[str, ...]] = {}
    source_first = True
    for query in _SOURCE_FIRST_QUERIES:
        hits = runtime.pedagogy.search_catalog(query, limit=3)
        types = tuple(hit.entity_type for hit in hits)
        regression_tops[query] = types
        source_first &= len(types) >= 2 and sum(kind == "source" for kind in types) >= 2
    metrics["source_first_regression_top3_types"] = regression_tops
    check("source_first_regression_queries", lambda: (
        source_first,
        "capital/decorators/backpropagation each expose at least two real sources in top 3",
    ))

    analyzer = SnippetAnalyzer()
    golden = _golden_snippets()
    golden_results = [analyzer.analyze(SnippetRequestDTO(
        text=snippet, action=SnippetAction.FIND_PROBLEMS,
    )) for snippet in golden]
    golden_passes = sum(
        result.detected_language == "python" and result.node_count > 0
        and bool(result.functions or result.classes)
        and bool(result.cfg_blocks) and bool(result.complexity_findings)
        for result in golden_results
    )
    metrics["analyzer_golden_cases"] = len(golden)
    metrics["analyzer_golden_passes"] = golden_passes
    check("deep_static_analyzer_golden_50", lambda: (
        len(golden) == golden_passes == 50,
        f"{golden_passes}/{len(golden)} snippets expose symbols/CFG/complexity",
    ))

    hostile = "import subprocess, socket, urllib.request\nvalue = eval('1+1')\nsubprocess.Popen(['x'])\nsocket.socket()\nurllib.request.urlopen('https://invalid')"
    with (
        patch.object(subprocess, "Popen", side_effect=AssertionError("execution")) as popen,
        patch.object(socket, "socket", side_effect=AssertionError("network")) as sock,
        patch.object(urllib.request, "urlopen", side_effect=AssertionError("network")) as urlopen,
        patch.object(builtins, "eval", side_effect=AssertionError("eval")) as eval_call,
        patch.object(builtins, "exec", side_effect=AssertionError("exec")) as exec_call,
    ):
        hostile_result = analyzer.analyze(SnippetRequestDTO(
            text=hostile, action=SnippetAction.FIND_PROBLEMS,
        ))
    blocked_calls = sum(mock.call_count for mock in (popen, sock, urlopen, eval_call, exec_call))
    metrics["analyzer_execution_boundary_calls"] = blocked_calls
    check("static_analysis_never_executes", lambda: (
        blocked_calls == 0 and len(hostile_result.security_findings) >= 4,
        f"boundary calls={blocked_calls}; security findings={len(hostile_result.security_findings)}",
    ))

    viewports = (
        (1024, 768, 1.0), (1366, 768, 1.0),
        (1920, 1080, 1.0), (1222, 956, 1.5),
    )
    profiles = [book_workspace_profile(width, height, density=density)
                for width, height, density in viewports]
    metrics["book_workspace_profiles"] = [
        {"mode": item.mode, "editor_dp": item.editor_width_dp,
         "support_dp": item.support_width_dp, "terminal_ratio": item.terminal_ratio}
        for item in profiles
    ]
    check("responsive_book_workspace_contract", lambda: (
        all(item.mode == "book" and item.editor_width_dp >= 360
            and item.support_width_dp >= 320 and .20 <= item.terminal_ratio <= .35
            for item in profiles),
        "four release viewport policies retain two pages and bounded transversal terminal",
    ))

    renderer = OfflineMathRenderer(data_directory / "math-audit-cache")
    rendered = [renderer.render(FormulaRenderRequest(
        latex=formula, spoken="fórmula matemática acessível", variables={},
        theme=theme, dpi=144,
    )) for theme in ("light", "dark", "contrast") for formula in _FORMULAS]
    cache_repeat = renderer.render(FormulaRenderRequest(
        latex=_FORMULAS[0], spoken="fórmula matemática acessível", variables={},
        theme="dark", dpi=144,
    ))
    metrics["math_render_snapshots"] = len(rendered)
    check("offline_math_contract", lambda: (
        all(not item.error and item.path is not None and item.path.is_file()
            and item.path.stat().st_size > 0 for item in rendered)
        and cache_repeat.cache_key == rendered[len(_FORMULAS)].cache_key,
        f"{len(rendered)} offline theme/family renders and deterministic cache key",
    ))

    normalizer = TextNormalizationService()
    text_passes = 0
    text_passes += normalizer.normalize("ação € → ≤ α", TextProfile.PROSE).text == "ação € → ≤ α"
    text_passes += normalizer.decode_python(b"# -*- coding: cp1252 -*-\nnome = 'a\xe7\xe3o'\n").encoding == "cp1252"
    text_passes += normalizer.decode_web("ação".encode(), content_type="text/html; charset=utf-8").text == "ação"
    try:
        normalizer.normalize("valor \ufffd", TextProfile.PROSE)
    except TextDecodingError:
        text_passes += 1
    metrics["text_contract_passes"] = text_passes
    check("loss_aware_text_contract", lambda: (
        text_passes == 4,
        f"{text_passes}/4 Unicode/declared-code/Web/quarantine contracts passed",
    ))

    passed = all(item["passed"] for item in checks.values())
    return {
        "audit_version": "iteration-21.0",
        "iteration": 21,
        "platform_scope": "Windows desktop only; mobile subtree frozen",
        "passed": passed,
        "checks": checks,
        "metrics": metrics,
        "privacy": {
            "aggregate_only": True,
            "temporary_profile": True,
            "contains_user_content": False,
            "contains_user_identifiers": False,
            "contains_paths": False,
        },
        "external_release_gates": {
            "windows_visual_matrix_physical": "requires physical 1024/1366/1920 and 100-200% DPI review",
            "keyboard_mouse_and_screen_reader": "requires physical assistive-technology review",
            "mixed_dpi_multi_monitor": "requires two physical monitors",
            "authenticode": "requires a publisher certificate",
        },
        "duration_ms": round((time.perf_counter() - started) * 1_000, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit Aprendix desktop Iteration 21")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if args.data_dir:
        report = audit(args.data_dir.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="aprendix-iteration21-") as temporary:
            report = audit(Path(temporary))
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(output)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
