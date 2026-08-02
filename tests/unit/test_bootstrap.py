"""Composition-root smoke tests with isolated platform data."""

from pathlib import Path

from aprendix.bootstrap import _snapshot, build_runtime
from aprendix.presentation.gui import LearningGuiController


def test_build_runtime_uses_requested_directory_and_wires_graph(
    tmp_path: Path,
) -> None:
    runtime = build_runtime(tmp_path / "app-data")

    assert runtime.database.path == (tmp_path / "app-data" / "aprendix.db").resolve()
    assert len(runtime.exercises.list_all()) == 23
    snapshot = runtime.graph_snapshot_service.get_snapshot(runtime.user.id)
    assert len(snapshot.nodes) == 6
    assert len(snapshot.recommendations) == 3

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
    assert len(controller.dashboard().nodes) == 6
