"""Local D3 renderer and GUI-controller tests."""

from pathlib import Path
from uuid import uuid4

from aprendix.application.contracts import ExerciseDTO, UserDTO
from aprendix.presentation import gui
from aprendix.presentation import graph_webview
from aprendix.presentation.graph_webview import GraphDocumentRenderer
from aprendix.presentation.gui import LearningGuiController


def test_graph_document_bundles_d3_and_escapes_html_payload() -> None:
    html = GraphDocumentRenderer().render(
        {
            "nodes": [
                {
                    "id": "n1",
                    "title": "</script><script>bad()</script>",
                    "difficulty": 0,
                    "mastery": 0.5,
                }
            ],
            "edges": [],
        }
    )

    assert "d3.forceSimulation" in html
    assert "\\u003c/script>" in html
    assert "__GRAPH_DATA__" not in html
    assert "__D3_SOURCE__" not in html


def test_gui_controller_submits_through_application_service() -> None:
    exercise = ExerciseDTO(
        graph_node_id=uuid4(),
        slug="test-exercise",
        title="Test",
        prompt="Prompt",
    )

    class Catalog:
        def list_all(self):
            return (exercise,)

    class SubmissionService:
        def __init__(self):
            self.command = None

        def submit(self, command):
            self.command = command
            return type(
                "Receipt",
                (),
                {"attempt_id": command.attempt_id},
            )()

    service = SubmissionService()
    controller = LearningGuiController(
        user=UserDTO(),
        exercises=Catalog(),
        submissions=service,
        snapshot_provider=lambda: {"nodes": [], "edges": []},
    )

    controller.submit(exercise.id, "print(1)", 10)

    assert service.command.exercise_id == exercise.id
    assert service.command.source_code == "print(1)"


def test_controller_opens_graph_without_spawning_another_application(
    monkeypatch,
) -> None:
    snapshot = {"nodes": [], "edges": []}
    opened = []
    monkeypatch.setattr(gui, "open_graph_view", opened.append)
    controller = LearningGuiController(
        user=UserDTO(),
        exercises=type("Catalog", (), {"list_all": lambda self: ()})(),
        submissions=object(),
        snapshot_provider=lambda: snapshot,
    )

    controller.open_graph()

    assert opened == [snapshot]


def test_graph_view_writes_offline_html_and_uses_default_browser(
    tmp_path: Path, monkeypatch,
) -> None:
    opened = []
    monkeypatch.setattr(graph_webview.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(
        graph_webview.webbrowser, "open_new_tab", lambda uri: opened.append(uri) or True
    )

    graph_webview.open_graph_view({"nodes": [], "edges": []})

    document = tmp_path / "aprendix-knowledge-graph.html"
    assert document.is_file()
    assert "Grafo de Conhecimento" in document.read_text(encoding="utf-8")
    assert opened == [document.as_uri()]
