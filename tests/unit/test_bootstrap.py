"""Composition-root smoke tests with isolated platform data."""

from pathlib import Path

import pytest

from aprendix import bootstrap
from aprendix.bootstrap import _snapshot, build_runtime
from aprendix.infrastructure.db import Database, DatabaseConfig
from aprendix.infrastructure.db.schema import SCHEMA_VERSION
from aprendix.presentation.gui import LearningGuiController


def test_build_runtime_uses_requested_directory_and_wires_graph(
    tmp_path: Path,
) -> None:
    runtime = build_runtime(tmp_path / "app-data")

    assert runtime.database.path == (tmp_path / "app-data" / "aprendix.db").resolve()
    assert len(runtime.exercises.list_all()) == 3563
    snapshot = runtime.graph_snapshot_service.get_snapshot(runtime.user.id)
    assert len(snapshot.nodes) == 4399
    assert len(snapshot.recommendations) == 3
    with runtime.database.read_connection() as connection:
        for recommendation in snapshot.recommendations:
            assert connection.execute(
                "SELECT 1 FROM exercises WHERE graph_node_id=? LIMIT 1",
                (str(recommendation.node_id),),
            ).fetchone() is not None

    serialized = _snapshot(runtime)
    assert all(
        "mastery" not in node["statistics"] for node in serialized["nodes"]
    )
    controller = LearningGuiController(
        user=runtime.user,
        exercises=runtime.exercises,
        submissions=runtime.submission_service,
        snapshot_provider=lambda: serialized,
    )
    assert len(controller.dashboard().nodes) == 4399
    assert runtime.platform.feature_enabled("ide.debugger") is True
    assert runtime.platform.metrics("runtime.startup", limit=1)[0].value > 0
    assert runtime.platform.health().status.value == "healthy"


def test_build_runtime_falls_back_to_compatible_profile_when_default_is_newer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared_root = tmp_path / "Aprendix"
    initial = Database(DatabaseConfig(shared_root / "aprendix.db"))
    initial.initialize()
    with initial.transaction() as connection:
        connection.execute(
            "INSERT INTO schema_migrations(version) VALUES (?)",
            (SCHEMA_VERSION + 1,),
        )

    monkeypatch.setattr(bootstrap, "default_data_directory", lambda: shared_root)

    runtime = build_runtime()

    expected = (
        shared_root / "profiles" / f"schema-v{SCHEMA_VERSION}" / "aprendix.db"
    ).resolve()
    warning = shared_root / "schema-compatibility-warning.txt"
    assert runtime.database.path == expected
    assert warning.is_file()
    assert f"schema version: {SCHEMA_VERSION}" in warning.read_text(encoding="utf-8")
