"""Buildozer entry point for the Aprendix mobile GUI."""

import sys
from pathlib import Path

source_root = Path(__file__).resolve().parent / "src"
mobile_root = Path(__file__).resolve().parent / "mobile"
if source_root.is_dir():
    sys.path.insert(0, str(source_root))
if mobile_root.is_dir():
    sys.path.insert(0, str(mobile_root))

if "ANDROID_ARGUMENT" in __import__("os").environ or sys.platform == "ios":
    from aprendix_mobile.app import launch_mobile

    raise SystemExit(launch_mobile())

if "--version" in sys.argv:
    from aprendix import __version__

    print(__version__)
    raise SystemExit(0)

if "--aprendix-grader" in sys.argv:
    from aprendix.infrastructure.grading import packaged_grader_main

    raise SystemExit(packaged_grader_main())

if "--aprendix-sandbox" in sys.argv:
    from aprendix.infrastructure.sandbox.python_sandbox import packaged_sandbox_main

    raise SystemExit(packaged_sandbox_main())

if "--aprendix-debugger" in sys.argv:
    from aprendix.infrastructure.debugger import packaged_debugger_main

    raise SystemExit(packaged_debugger_main())

if "--self-test" in sys.argv:
    import json
    import tempfile
    from aprendix.bootstrap import build_runtime
    from aprendix.application.games import MinesweeperGame, SudokuGame
    from aprendix.application.contracts import SnippetRequestDTO, TutorRequestDTO
    from aprendix.infrastructure.db.schema import SCHEMA_VERSION

    target = Path(tempfile.mkdtemp(prefix="aprendix-self-test-"))
    if "--data-dir" in sys.argv:
        position = sys.argv.index("--data-dir")
        if position + 1 >= len(sys.argv):
            raise SystemExit(2)
        target = Path(sys.argv[position + 1])
    runtime = build_runtime(target)
    result = runtime.desktop.run("print(6 * 7)")
    with runtime.database.read_connection() as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        schema = connection.execute("SELECT max(version) FROM schema_migrations").fetchone()[0]
        facts = connection.execute(
            """SELECT count(*) FROM theory_cards tc JOIN document_chunks c ON c.id=tc.chunk_id
               JOIN documents d ON d.id=c.document_id
               WHERE d.source_path='aprendix://authored-facts/v1'"""
        ).fetchone()[0]
    glossary_ok = bool(runtime.curriculum.glossary("else", limit=1))
    games_ok = len(SudokuGame("Fácil", 1).fixed) > 0 and len(MinesweeperGame("Fácil", 1).mines) == 10
    tutor_result = runtime.tutor.answer(TutorRequestDTO(
        question="Como funciona o operador módulo em Python?"
    ))
    snippet_result = runtime.snippets.analyze(SnippetRequestDTO(
        text="def dobro(x):\n    return x * 2"
    ))
    project_templates = runtime.portfolio.templates()
    track_slugs = {track["slug"] for track in runtime.curriculum.tracks()}
    # Some tracks intentionally offer both a guided project and a capstone.
    # Validate complete track coverage instead of requiring a 1:1 count.
    projects_ok = (
        len(project_templates) >= len(track_slugs) >= 12
        and track_slugs.issubset({template.track_slug for template in project_templates})
    )
    game_session = runtime.games.new("sudoku", "Fácil", daily=True)
    extended_ok = all((
        not tutor_result.declined, bool(tutor_result.evidence),
        snippet_result.detected_language == "python", projects_ok,
        game_session.id is not None,
    ))
    health = runtime.platform.health()
    feature_flags = runtime.platform.feature_flags()
    passed = all((result.status == "ok", result.stdout.strip() == "42", integrity == "ok",
                  schema == SCHEMA_VERSION, facts >= 48, glossary_ok, games_ok,
                  health.status.value == "healthy", len(feature_flags) >= 14,
                  extended_ok))
    (target / "self-test-report.json").write_text(
        json.dumps({"passed": passed, "sandbox": result.model_dump(mode="json"),
                    "integrity": integrity, "schema_version": schema,
                    "authored_fact_cards": facts, "dictionary_else": glossary_ok,
                    "games": games_ok, "extended_features": extended_ok,
                    "tutor_confidence": tutor_result.confidence,
                    "projects": len(project_templates),
                    "runtime_health": health.status.value,
                    "feature_flags": len(feature_flags)},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    raise SystemExit(0 if passed else 3)

if sys.platform == "win32":
    from aprendix.presentation.startup_splash import start_startup_splash

    start_startup_splash()

from aprendix.bootstrap import gui_main

raise SystemExit(gui_main())
