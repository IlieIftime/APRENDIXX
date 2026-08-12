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
        graph_service: Any | None = None,
        search_service: Any | None = None,
        card_provider: Callable[[], tuple[Any, ...]] | None = None,
        corrector: Any | None = None,
        desktop: Any | None = None,
        cluster_provider: Callable[[], tuple[Any, ...]] | None = None,
        curriculum: Any | None = None,
        knowledge_structure: Any | None = None,
        progress: Any | None = None,
        tutor: Any | None = None,
        portfolio: Any | None = None,
        snippets: Any | None = None,
        games: Any | None = None,
        content_updates: Any | None = None,
        profile_transfer: Any | None = None,
        quality: Any | None = None,
        governance: Any | None = None,
        pedagogy: Any | None = None,
        asset_store: Any | None = None,
    ) -> None:
        self.user = user
        self._exercises = exercises
        self._submissions = submissions
        self._snapshot_provider = snapshot_provider
        self._graph_service = graph_service
        self._search_service = search_service
        self._card_provider = card_provider or (lambda: ())
        self._corrector = corrector
        self._desktop = desktop
        self._cluster_provider = cluster_provider or (lambda: ())
        self._curriculum = curriculum
        self._knowledge_structure = knowledge_structure
        self._progress = progress
        self._tutor = tutor
        self._portfolio = portfolio
        self._snippets = snippets
        self._games = games
        self._content_updates = content_updates
        self._profile_transfer = profile_transfer
        self._quality = quality
        self._governance = governance
        self._pedagogy = pedagogy
        self._asset_store = asset_store

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
        snapshot = self.visible_graph() if self._graph_service is not None else self.snapshot()
        open_graph_view(snapshot)

    def snapshot(self) -> Mapping[str, Any]:
        return self._snapshot_provider()

    def dashboard(self):
        snapshot = GraphSnapshotDTO.model_validate(self._snapshot_provider())
        if self._progress is not None and hasattr(self._progress, "curriculum_node_ids"):
            curriculum_ids = set(self._progress.curriculum_node_ids())
            snapshot = snapshot.model_copy(update={
                "nodes": tuple(
                    node for node in snapshot.nodes if node.id in curriculum_ids
                ),
                "recommendations": tuple(
                    item for item in snapshot.recommendations
                    if item.node_id in curriculum_ids
                ),
            })
        return DashboardService.from_snapshot(snapshot)

    def dashboard_analytics(
        self, *, period_days: int = 30, start=None, end=None,
        track_slug: str | None = None, node_id: UUID | None = None,
    ):
        if self._progress is None or not hasattr(self._progress, "analytics"):
            raise RuntimeError("Analytics de progresso indisponíveis.")
        return self._progress.analytics(
            self.user.id, period_days=period_days, start=start, end=end,
            track_slug=track_slug, node_id=node_id,
        )

    def visible_graph(
        self, *, period_days: int = 30, start=None, end=None,
        include_eligible: bool = False, node_limit: int = 150,
        edge_limit: int = 300,
    ):
        if self._graph_service is None:
            return self.snapshot()
        return self._graph_service.get_visible_snapshot(
            self.user.id, period_days=period_days, start=start, end=end,
            include_eligible=include_eligible,
            node_limit=node_limit, edge_limit=edge_limit,
        )

    def node_analytics(
        self, node_id: UUID, *, period_days: int = 30, start=None, end=None,
    ):
        if self._graph_service is None:
            raise RuntimeError("Analytics do grafo indisponíveis.")
        return self._graph_service.node_analytics(
            self.user.id, node_id, period_days=period_days,
            start=start, end=end,
        )

    def personal_progress(self):
        if self._progress is None:
            raise RuntimeError("Motor de progresso indisponível.")
        return self._progress.progress(self.user.id)

    def next_action(self, available_minutes: int = 25):
        if self._progress is None:
            return None
        if hasattr(self._progress, "action_for_time"):
            return self._progress.action_for_time(self.user.id, available_minutes)
        return self._progress.best_next_action(self.user.id, available_minutes=available_minutes)

    def weekly_plan(self):
        if self._progress is None:
            return ()
        return self._progress.build_weekly_plan(self.user.id)

    def progress_forecast(self):
        if self._progress is None:
            return None
        return self._progress.forecast(self.user.id)

    def weekly_progress_report(self):
        if self._progress is None:
            return None
        return self._progress.weekly_report(self.user.id)

    def complete_weekly_item(self, item_id, completed: bool = True):
        if self._progress is None:
            return False
        return self._progress.complete_plan_item(self.user.id, item_id, completed)

    def theory_cards(self, **filters):
        # The curiosity deck must never turn arbitrary imported PDF chunks into
        # pedagogical claims. Imported material remains available in Search/Reader.
        filters.setdefault("authored_only", True)
        return self._card_provider(**filters)

    def pedagogical_document(self, owner_type: str, owner_id: str):
        return self._pedagogy.get(owner_type, str(owner_id)) if self._pedagogy else None

    def pedagogical_asset_path(self, asset_id: str):
        if self._pedagogy is None or self._asset_store is None:
            return None
        getter = getattr(self._pedagogy, "get_asset", None)
        if getter is None:
            return None
        asset = getter(asset_id)
        return self._asset_store.materialize(asset) if asset is not None else None

    def clusters(self):
        return self._cluster_provider()

    def tracks(self):
        return self._curriculum.tracks() if self._curriculum else ()

    def learning_paths(self):
        return self._curriculum.paths() if self._curriculum else ()

    def curriculum_audit(self):
        return self._curriculum.audit() if self._curriculum else {"valid": False}

    def progress_integrity_audit(self):
        return (
            self._curriculum.progress_integrity_audit()
            if self._curriculum else {"valid": 0, "suspicious": 0}
        )

    def pedagogical_quality(self):
        return self._quality.summary() if self._quality else None

    def bibliography_coverage(self):
        return self._governance.bibliography_coverage() if self._governance else None

    def diagnostic_exercises(self, *, limit: int = 5):
        return self._curriculum.diagnostic(limit=limit) if self._curriculum else ()

    def units(self, track_slug: str):
        return self._curriculum.units(track_slug) if self._curriculum else ()

    def course_practice(self, track_slug: str):
        """Return the ordered IDE journey for one curriculum track."""

        if self._curriculum is None:
            return ()
        exercises = {str(item.id): item for item in self._exercises.list_all()}
        units = tuple(self._curriculum.units(track_slug))
        theory_by_chapter = {}
        assessments_by_chapter = {}
        for unit in units:
            if unit.get("kind") == "theory":
                theory_by_chapter.setdefault(unit.get("chapter_title", ""), unit)
            if unit.get("kind") in {"quiz", "hybrid"} and unit.get("assessment_id"):
                assessments_by_chapter.setdefault(unit.get("chapter_title", ""), []).append({
                    "unit_id": unit["id"],
                    "assessment_id": unit["assessment_id"],
                    "kind": unit["kind"],
                    "title": unit.get("title", "Teste de etapa"),
                    "completed": bool(unit["completed"]),
                    "unlocked": bool(unit["unlocked"]),
                })
        journey = []
        current_theory = None
        for unit in units:
            if unit.get("kind") == "theory":
                current_theory = unit
                continue
            exercise_id = unit.get("exercise_id")
            exercise = exercises.get(str(exercise_id)) if exercise_id else None
            if unit.get("kind") != "practice" or exercise is None:
                continue
            theory = theory_by_chapter.get(unit.get("chapter_title", "")) or current_theory or {}
            journey.append({
                "exercise": exercise,
                "unit_id": unit["id"],
                "chapter_title": unit["chapter_title"],
                "completed": bool(unit["completed"]),
                "unlocked": bool(unit["unlocked"]),
                "theory_unit_id": theory.get("id", ""),
                "theory_title": theory.get("title") or unit["chapter_title"],
                "theory_body": theory.get("body", ""),
                "theory_example": theory.get("example", ""),
                "assessments": tuple(
                    assessments_by_chapter.get(unit.get("chapter_title", ""), ())
                ),
            })
        return tuple(journey)

    def glossary(self, term: str, *, limit: int = 8):
        return self._curriculum.glossary(term, limit=limit) if self._curriculum else ()

    def ask_tutor(self, request):
        if self._tutor is None:
            raise RuntimeError("Tutor offline indisponível.")
        return self._tutor.answer(request)

    def tutor_history(self, *, limit: int = 50):
        return self._tutor.history(limit=limit) if self._tutor else ()

    def delete_tutor_history(self):
        return self._tutor.delete_history() if self._tutor else 0

    def project_templates(self):
        return self._portfolio.templates() if self._portfolio else ()

    def portfolio_entries(self):
        return self._portfolio.entries() if self._portfolio else ()

    def project_context(self, project_id):
        if self._portfolio is None: raise RuntimeError("Portefólio indisponível.")
        return self._portfolio.context(project_id)

    def start_guided_project(self, template_id: str, *, mode: str = "guided"):
        if self._portfolio is None: raise RuntimeError("Portefólio indisponível.")
        return self._portfolio.start(template_id, mode=mode)

    def evaluate_project(self, project_id):
        if self._portfolio is None: raise RuntimeError("Portefólio indisponível.")
        return self._portfolio.evaluate(project_id)

    def export_project(self, project_id, destination):
        if self._portfolio is None: raise RuntimeError("Portefólio indisponível.")
        return self._portfolio.export_zip(project_id, destination)

    def analyze_snippet(self, request):
        if self._snippets is None: raise RuntimeError("Analisador local indisponível.")
        return self._snippets.analyze(request)

    def extract_snippet_image(self, path):
        if self._snippets is None: raise RuntimeError("OCR local indisponível.")
        return self._snippets.extract_image(path)

    def delete_snippet_history(self):
        return self._snippets.delete_history() if self._snippets else 0

    def new_game(self, game: str, difficulty: str, *, daily: bool = False):
        return self._games.new(game, difficulty, daily=daily) if self._games else None

    def resume_game(self, game: str, difficulty: str):
        return self._games.resume(game, difficulty) if self._games else None

    def save_game(self, session):
        return self._games.save(session) if self._games else None

    def finish_game(self, session):
        return self._games.finish(session) if self._games else None

    def game_statistics(self):
        return self._games.statistics() if self._games else ()

    def export_profile(self, destination, passphrase: str):
        if self._profile_transfer is None:
            raise RuntimeError("Transferência de perfil indisponível.")
        return self._profile_transfer.export(destination, passphrase)

    def preview_profile(self, source, passphrase: str):
        if self._profile_transfer is None:
            raise RuntimeError("Transferência de perfil indisponível.")
        return self._profile_transfer.preview(source, passphrase)

    def import_profile(self, source, passphrase: str):
        if self._profile_transfer is None:
            raise RuntimeError("Transferência de perfil indisponível.")
        return self._profile_transfer.import_file(source, passphrase)

    def inspect_content_pack(self, source):
        if self._content_updates is None:
            raise RuntimeError("Gestor de conteúdo indisponível.")
        return self._content_updates.inspect(source)

    def install_content_pack(self, source):
        if self._content_updates is None:
            raise RuntimeError("Gestor de conteúdo indisponível.")
        return self._content_updates.install(source)

    def installed_content_packs(self):
        return self._content_updates.installed() if self._content_updates else ()

    def rollback_content_pack(self, pack_id: str, version: str):
        if self._content_updates is None:
            raise RuntimeError("Gestor de conteúdo indisponível.")
        return self._content_updates.rollback(pack_id, version)

    def check_content_updates(
        self, registry_url: str, *, force: bool = False,
        wifi_only: bool = False, external_power_only: bool = False,
        unmetered: bool | None = None, external_power: bool | None = None,
    ):
        if self._content_updates is None:
            raise RuntimeError("Gestor de conteúdo indisponível.")
        result = self._content_updates.check_remote(
            registry_url, force=force, wifi_only=wifi_only,
            external_power_only=external_power_only, unmetered=unmetered,
            external_power=external_power,
        )
        self._remote_content_offers = {
            f"{offer.pack_id}@{offer.version}": offer for offer in result.get("offers", ())
        }
        return {
            **result,
            "offers": tuple({
                "identity": identity,
                "title": offer.title,
                "summary": offer.summary,
                "size": offer.size,
                "sources": offer.sources,
                "affected_tracks": offer.affected_tracks,
                "published_at": offer.published_at,
            } for identity, offer in self._remote_content_offers.items()),
        }

    def install_remote_content_pack(self, identity: str, registry_url: str):
        if self._content_updates is None:
            raise RuntimeError("Gestor de conteúdo indisponível.")
        try:
            offer = self._remote_content_offers[identity.strip()]
        except (AttributeError, KeyError) as exc:
            raise ValueError("Consulta primeiro o registo e escolhe pack-id@versão.") from exc
        return self._content_updates.install_remote(offer, registry_url)

    def preview_remote_content_pack(self, identity: str, registry_url: str):
        if self._content_updates is None:
            raise RuntimeError("Gestor de conteúdo indisponível.")
        try:
            offer = self._remote_content_offers[identity.strip()]
        except (AttributeError, KeyError) as exc:
            raise ValueError("Consulta primeiro o registo e escolhe pack-id@versão.") from exc
        return self._content_updates.preview_remote(offer, registry_url)

    def assessment(self, item_id: str):
        if self._curriculum is None: raise RuntimeError("Currículo indisponível.")
        return self._curriculum.assessment(item_id)

    def answer_assessment(self, item_id: str, answer: str, **kwargs):
        if self._curriculum is None: raise RuntimeError("Currículo indisponível.")
        return self._curriculum.answer(item_id, answer, **kwargs)

    def complete_unit(self, unit_id: str):
        if self._curriculum is None: raise RuntimeError("Currículo indisponível.")
        return self._curriculum.complete_unit(unit_id)

    def search(self, request: SearchRequestDTO, cancellation=None):
        if self._search_service is None:
            raise RuntimeError("O índice de conhecimento ainda não está disponível.")
        if cancellation is None:
            return self._search_service.search(request)
        return self._search_service.search(request, cancellation)

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

    def toggle_reading_bookmark(self, evidence_id: str) -> bool:
        if self._knowledge_structure is None:
            raise RuntimeError("Leitor pedagógico indisponível.")
        return self._knowledge_structure.toggle_bookmark(self.user.id, evidence_id)

    def reading_bookmarks(self):
        return (
            self._knowledge_structure.bookmarks(self.user.id)
            if self._knowledge_structure else ()
        )

    def save_reading_note(self, evidence_id: str, note: str, **selection):
        if self._knowledge_structure is None:
            raise RuntimeError("Leitor pedagógico indisponível.")
        return self._knowledge_structure.save_note(
            self.user.id, evidence_id, note, **selection
        )

    def reading_notes(self, evidence_id: str):
        return (
            self._knowledge_structure.notes(self.user.id, evidence_id)
            if self._knowledge_structure else ()
        )

    def compare_readings(self, evidence_ids: tuple[str, ...], *, query: str = ""):
        if self._knowledge_structure is None:
            raise RuntimeError("Leitor pedagógico indisponível.")
        return self._knowledge_structure.compare_readings(evidence_ids, query=query)

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

    def debug_code(self, request, exercise_id=None):
        return self._desktop_service().debug(request, exercise_id)

    def evaluate(self, exercise, source_code: str, duration_ms: int, **kwargs):
        return self._desktop_service().evaluate(
            exercise, source_code, duration_ms, **kwargs
        )

    def learning_session(self, exercise_id):
        return self._desktop_service().learning_session(exercise_id)

    def update_learning_session(self, exercise_id, **changes):
        return self._desktop_service().update_learning_session(exercise_id, **changes)

    def learning_session_summary(self):
        return self._desktop_service().learning_session_summary()

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

    def review_card(
        self, card_id: UUID, *, known: bool | None = None, feedback: str | None = None,
    ):
        return self._desktop_service().review_card(
            card_id, known=known, feedback=feedback,
        )

    def daily_card_ids(self, *, limit: int = 30):
        return self._desktop_service().daily_card_ids(limit=limit)

    def projects(self):
        return self._desktop_service().projects()

    def project_files(self, project_id):
        return self._desktop_service().project_files(project_id)

    def project_versions(self, project_id, relative_path="main.py"):
        return self._desktop_service().project_versions(project_id, relative_path)

    def save_debug_recovery(self, exercise_id, source, **state):
        return self._desktop_service().save_debug_recovery(exercise_id, source, **state)

    def load_debug_recovery(self, exercise_id):
        return self._desktop_service().load_debug_recovery(exercise_id)

    def debug_history(self, *, limit: int = 30):
        return self._desktop_service().debug_history(limit=limit)

    def test_history(self, *, limit: int = 30):
        return self._desktop_service().test_history(limit=limit)

    def save_project(
        self, name: str, source_code: str, project_id=None, *, relative_path="main.py",
    ):
        return self._desktop_service().save_project(
            name, source_code, project_id, relative_path=relative_path,
        )

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
