"""BeeWare/Toga shell used by the Briefcase iOS package."""

from __future__ import annotations

import time

from aprendix.presentation.graph_webview import GraphDocumentRenderer
from aprendix.presentation.gui import LearningGuiController


class TogaDependencyError(RuntimeError):
    """Raised when the native BeeWare toolkit is unavailable."""


def launch_toga(controller: LearningGuiController) -> int:
    try:
        import toga
        from toga.style import Pack
        from toga.style.pack import COLUMN, ROW
    except ImportError as exc:
        raise TogaDependencyError(
            "Toga is not installed; use the Briefcase iOS environment"
        ) from exc

    catalogue = controller.exercises()
    selected = [catalogue[0] if catalogue else None]
    started = [time.monotonic()]

    def startup(_app):
        prompt = toga.Label(
            selected[0].prompt if selected[0] else "Sem exercícios disponíveis.",
            style=Pack(padding=8),
        )
        editor = toga.MultilineTextInput(
            value=selected[0].starter_code if selected[0] else "",
            style=Pack(flex=1, padding=8),
        )
        status = toga.Label("Pronto", style=Pack(padding=8))
        graph = toga.WebView(
            content=GraphDocumentRenderer().render(controller.snapshot()),
            style=Pack(flex=1, padding=8),
        )

        def select_exercise(exercise):
            selected[0] = exercise
            prompt.text = exercise.prompt
            editor.value = exercise.starter_code
            started[0] = time.monotonic()

        def submit(_widget):
            exercise = selected[0]
            source = editor.value or ""
            if exercise is None or not source.strip():
                status.text = "Escreve algum código antes de guardar."
                return
            duration_ms = max(0, round((time.monotonic() - started[0]) * 1000))
            receipt = controller.submit(exercise.id, source, duration_ms)
            status.text = f"Guardado localmente: {receipt.attempt_id}"
            graph.content = GraphDocumentRenderer().render(controller.snapshot())

        exercise_buttons = toga.Box(style=Pack(direction=ROW, padding=4))
        for exercise in catalogue:
            exercise_buttons.add(
                toga.Button(
                    exercise.title,
                    on_press=lambda _widget, item=exercise: select_exercise(item),
                    style=Pack(flex=1, padding=4),
                )
            )
        controls = toga.Box(
            children=[
                toga.Button(
                    "Guardar tentativa",
                    on_press=submit,
                    style=Pack(flex=1, padding=4),
                )
            ],
            style=Pack(direction=ROW),
        )
        return toga.Box(
            children=[
                exercise_buttons,
                prompt,
                editor,
                controls,
                status,
                graph,
            ],
            style=Pack(direction=COLUMN, flex=1, padding=8),
        )

    app = toga.App(
        "Aprendix",
        "io.aprendix.aprendix",
        startup=startup,
    )
    app.main_loop()
    return 0
