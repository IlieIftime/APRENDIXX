"""Optional Kivy GUI backed exclusively by application-facing contracts."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from aprendix.application.contracts import (
    GraphSnapshotDTO,
    SearchRequestDTO,
    SmartCorrectionRequestDTO,
    SubmissionReceipt,
    SubmitAttemptCommand,
    UserDTO,
)
from aprendix.application.knowledge import DashboardService
from aprendix.application.ports import ExerciseCatalog
from aprendix.application.services import AttemptSubmissionService
from aprendix.presentation.graph_webview import open_graph_view


class GuiDependencyError(RuntimeError):
    """Raised when the optional GUI toolkit is unavailable."""


class LearningGuiController:
    """Presentation-neutral controller shared by desktop and native shells."""

    def __init__(
        self,
        *,
        user: UserDTO,
        exercises: ExerciseCatalog,
        submissions: AttemptSubmissionService,
        snapshot_provider: Callable[[], Mapping[str, Any]],
        search_service: Any | None = None,
        card_provider: Callable[[], tuple[Any, ...]] | None = None,
        corrector: Any | None = None,
        desktop: Any | None = None,
        cluster_provider: Callable[[], tuple[Any, ...]] | None = None,
        curriculum: Any | None = None,
        knowledge_structure: Any | None = None,
    ) -> None:
        self.user = user
        self._exercises = exercises
        self._submissions = submissions
        self._snapshot_provider = snapshot_provider
        self._search_service = search_service
        self._card_provider = card_provider or (lambda: ())
        self._corrector = corrector
        self._desktop = desktop
        self._cluster_provider = cluster_provider or (lambda: ())
        self._curriculum = curriculum
        self._knowledge_structure = knowledge_structure

    def exercises(self):
        return self._exercises.list_all()

    def submit(
        self, exercise_id: UUID, source_code: str, duration_ms: int
    ) -> SubmissionReceipt:
        return self._submissions.submit(
            SubmitAttemptCommand(
                user_id=self.user.id, exercise_id=exercise_id,
                source_code=source_code, duration_ms=duration_ms,
                submitted_at=datetime.now(UTC),
            )
        )

    def open_graph(self) -> None:
        # A multiprocessing child from a one-file PyInstaller GUI can execute
        # the application entry point again and create an endless window chain.
        # The graph is self-contained HTML, so open it directly in the browser.
        open_graph_view(dict(self._snapshot_provider()))

    def snapshot(self) -> Mapping[str, Any]:
        return self._snapshot_provider()

    def dashboard(self):
        return DashboardService.from_snapshot(
            GraphSnapshotDTO.model_validate(self._snapshot_provider())
        )

    def theory_cards(self, **filters):
        return self._card_provider(**filters)

    def clusters(self):
        return self._cluster_provider()

    def tracks(self):
        return self._curriculum.tracks() if self._curriculum else ()

    def units(self, track_slug: str):
        return self._curriculum.units(track_slug) if self._curriculum else ()

    def glossary(self, term: str, *, limit: int = 8):
        return self._curriculum.glossary(term, limit=limit) if self._curriculum else ()

    def assessment(self, item_id: str):
        if self._curriculum is None: raise RuntimeError("Currículo indisponível.")
        return self._curriculum.assessment(item_id)

    def answer_assessment(self, item_id: str, answer: str, **kwargs):
        if self._curriculum is None: raise RuntimeError("Currículo indisponível.")
        return self._curriculum.answer(item_id, answer, **kwargs)

    def complete_unit(self, unit_id: str):
        if self._curriculum is None: raise RuntimeError("Currículo indisponível.")
        return self._curriculum.complete_unit(unit_id)

    def search(self, request: SearchRequestDTO):
        if self._search_service is None:
            raise RuntimeError("O índice de conhecimento ainda não está disponível.")
        return self._search_service.search(request)

    def knowledge_areas(self):
        return self._knowledge_structure.areas() if self._knowledge_structure else ()

    def search_shortcuts(self, area_id: str | None = None, *, limit: int = 20):
        return (
            self._knowledge_structure.shortcuts(area_id, limit=limit)
            if self._knowledge_structure else ()
        )

    def curated_sources(self, area_ids: tuple[str, ...] = (), *, limit: int = 20):
        return (
            self._knowledge_structure.sources(area_ids, limit=limit)
            if self._knowledge_structure else ()
        )

    def reading_detail(self, evidence_id: str, *, query: str = ""):
        if self._knowledge_structure is None:
            raise RuntimeError("Leitor pedagógico indisponível.")
        return self._knowledge_structure.reading_detail(evidence_id, query=query)

    def correct(self, request: SmartCorrectionRequestDTO):
        if self._corrector is None:
            raise RuntimeError("O corretor inteligente ainda não está disponível.")
        return self._corrector.correct(request)

    def _desktop_service(self):
        if self._desktop is None:
            raise RuntimeError("O espaço de aprendizagem desktop não está disponível.")
        return self._desktop

    def run_code(self, source_code: str):
        return self._desktop_service().run(source_code)

    def evaluate(self, exercise, source_code: str, duration_ms: int, **kwargs):
        return self._desktop_service().evaluate(
            exercise, source_code, duration_ms, **kwargs
        )

    def variation(self, exercise, *, proficiency: float = 0.0):
        return self._desktop_service().variation(exercise, proficiency=proficiency)

    def copykate(self, source_code: str, previous_source: str = ""):
        return self._desktop_service().copykate_suggestions(source_code, previous_source)

    def autocomplete(self, source_code: str, cursor: int, *, proficiency: float = 0.0):
        return self._desktop_service().completion.suggest(
            source_code, cursor, proficiency=proficiency
        )

    def milestones(self):
        return self._desktop_service().milestones()

    def gamification(self):
        return self._desktop_service().gamification()

    def review_card(self, card_id: UUID, *, known: bool):
        return self._desktop_service().review_card(card_id, known=known)

    def projects(self):
        return self._desktop_service().projects()

    def save_project(self, name: str, source_code: str, project_id=None):
        return self._desktop_service().save_project(name, source_code, project_id)

    def record_focus(self, minutes: int, elapsed_seconds: int, status: str):
        return self._desktop_service().record_focus(minutes, elapsed_seconds, status)

    def save_draft(self, exercise_id: UUID, source_code: str):
        return self._desktop_service().save_draft(exercise_id, source_code)

    def load_draft(self, exercise_id: UUID):
        return self._desktop_service().load_draft(exercise_id)

    def save_preference(self, name: str, value: str):
        return self._desktop_service().save_preference(name, value)

    def load_preference(self, name: str, default: str = ""):
        return self._desktop_service().load_preference(name, default)

    def study_plan(self):
        return self._desktop_service().study_plan()

    def save_study_plan(self, *, start_date, weekly_hours: float, assessment_percent: int):
        return self._desktop_service().save_study_plan(
            start_date=start_date, weekly_hours=weekly_hours,
            assessment_percent=assessment_percent,
        )


def launch_kivy(controller: LearningGuiController) -> int:
    try:
        import kivy  # noqa: F401
    except ImportError as exc:
        raise GuiDependencyError(
            'Kivy is not installed; install Aprendix with the "gui" extra'
        ) from exc
    from aprendix.presentation.kivy_advanced import launch_advanced_kivy

    return launch_advanced_kivy(controller)
