"""Composition root that wires application, infrastructure, and presentation."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from aprendix.application.graph import GraphRecommender, GraphSnapshotService, GraphWorker
from aprendix.application.knowledge import (
    ExtractiveAnswerSynthesizer,
    FallbackAnswerSynthesizer,
    HybridSearchService,
)
from aprendix.application.smart_corrector import SmartCorrector
from aprendix.application.desktop import DesktopLearningService
from aprendix.application.curriculum import CurriculumService
from aprendix.application.clustering import HdbscanClusterService
from aprendix.application.contracts import EventDTO, SearchFiltersDTO, UserDTO
from aprendix.application.services import (
    AttemptSubmissionService,
    EventIngestionService,
)
from aprendix.domain import EventType
from aprendix.infrastructure.db import (
    AttemptRepository,
    Database,
    DatabaseConfig,
    EventRepository,
    ExerciseRepository,
    LearningRecordRepository,
    UserRepository,
    SQLiteGraphRepository,
    KnowledgeRepository,
    KnowledgeStructureRepository,
    DesktopRepository,
)
from aprendix.infrastructure.curriculum import CurriculumRepository
from aprendix.infrastructure.grading import IsolatedGradingExecutor, OopGradingPolicy
from aprendix.infrastructure.ingestion import FeatureHashEmbedding
from aprendix.infrastructure.local_llm import OllamaLocalSynthesizer
from aprendix.infrastructure.security import AesGcmFieldCipher, FileKeyStore
from aprendix.infrastructure.web_search import SafeDuckDuckGoSearch
from aprendix.infrastructure.seed import seed_advanced_catalog, seed_default_catalog
from aprendix.infrastructure.cache import EncryptedOfflineCache
from aprendix.infrastructure.sync import EncryptedSyncQueue
from aprendix.infrastructure.sandbox import PythonAstPolicy, PythonSandbox
from aprendix.presentation.cli import run_cli
from aprendix.presentation.gui import (
    GuiDependencyError,
    LearningGuiController,
    launch_kivy,
)


@dataclass(frozen=True, slots=True)
class Runtime:
    database: Database
    user: UserDTO
    events: EventRepository
    attempts: AttemptRepository
    exercises: ExerciseRepository
    event_service: EventIngestionService
    submission_service: AttemptSubmissionService
    graph_snapshot_service: GraphSnapshotService
    knowledge: KnowledgeRepository
    search_service: HybridSearchService
    corrector: SmartCorrector
    desktop: DesktopLearningService
    cluster_service: HdbscanClusterService
    cache: EncryptedOfflineCache
    sync_queue: EncryptedSyncQueue
    curriculum: CurriculumService
    knowledge_structure: KnowledgeStructureRepository


def default_data_directory() -> Path:
    """Resolve a platform app-data directory outside the source workspace."""

    if sys.platform == "win32":
        root = os.environ.get("LOCALAPPDATA")
        if root:
            return Path(root) / "Aprendix"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Aprendix"
    root = os.environ.get("XDG_DATA_HOME")
    return Path(root) / "aprendix" if root else Path.home() / ".local/share/aprendix"


def build_runtime(data_directory: Path | None = None) -> Runtime:
    """Construct a complete local runtime without starting a presentation loop."""

    data_directory = data_directory or default_data_directory()
    database = Database(DatabaseConfig(data_directory / "aprendix.db"))
    database.initialize()
    cipher = AesGcmFieldCipher.from_key_store(
        FileKeyStore(data_directory / "keys" / "fields.key")
    )
    seed_default_catalog(database)
    seed_advanced_catalog(database)

    users = UserRepository(database, cipher)
    event_repository = EventRepository(database, cipher)
    attempt_repository = AttemptRepository(database, cipher)
    user = users.first()
    if user is None:
        user = UserDTO(display_name="Aprendiz")
        users.add(user)
        EventIngestionService(event_repository).ingest(
            EventDTO(
                user_id=user.id,
                event_type=EventType.USER_CREATED,
                payload={"sync_consent": user.consent_sync},
            )
        )

    graph_repository = SQLiteGraphRepository(database)
    knowledge_repository = KnowledgeRepository(database, cipher)
    knowledge_structure = KnowledgeStructureRepository(database, cipher)
    knowledge_structure.seed()
    knowledge_repository.seed_authored_facts()
    knowledge_repository.audit_content_quality()
    if not knowledge_structure.mappings_current():
        knowledge_structure.ensure_mappings(
            knowledge_repository.search_candidates(SearchFiltersDTO(), limit=100_000)
        )
    graph_worker = GraphWorker(graph_repository)
    event_service = EventIngestionService(event_repository, observers=(graph_worker,))
    submission_service = AttemptSubmissionService(
        LearningRecordRepository(
            database,
            attempt_repository,
            event_repository,
        ),
        observers=(graph_worker,),
    )
    exercise_repository = ExerciseRepository(database, cipher)
    corrector = SmartCorrector(OopGradingPolicy(), IsolatedGradingExecutor())
    desktop_repository = DesktopRepository(database, cipher)
    desktop_repository.seed_milestones()
    curriculum_repository = CurriculumRepository(database, cipher)
    curriculum_repository.seed()
    with database.read_connection() as connection:
        chunk_count = int(connection.execute("SELECT count(*) FROM document_chunks").fetchone()[0])
        bibliography_count = int(connection.execute("SELECT count(*) FROM bibliography_links").fetchone()[0])
    if chunk_count and not bibliography_count:
        curriculum_repository.rebuild_bibliography_links()
    cache = EncryptedOfflineCache(data_directory / "cache", cipher)
    desktop = DesktopLearningService(
        user=user, exercises=exercise_repository, submissions=submission_service,
        attempts=attempt_repository, events=event_service,
        workspace=desktop_repository,
        sandbox=PythonSandbox(PythonAstPolicy(allow_classes=True)),
        corrector=corrector,
        cache=cache,
    )
    curriculum = CurriculumService(
        user=user, repository=curriculum_repository, events=event_service,
        web=SafeDuckDuckGoSearch(timeout_seconds=4.0),
    )
    return Runtime(
        database=database,
        user=user,
        events=event_repository,
        attempts=attempt_repository,
        exercises=exercise_repository,
        event_service=event_service,
        submission_service=submission_service,
        graph_snapshot_service=GraphSnapshotService(
            graph_repository,
            GraphRecommender(graph_repository),
        ),
        knowledge=knowledge_repository,
        search_service=HybridSearchService(
            knowledge_repository,
            embedder=FeatureHashEmbedding(),
            web=SafeDuckDuckGoSearch(),
            synthesizer=(
                FallbackAnswerSynthesizer(
                    OllamaLocalSynthesizer(os.environ["APRENDIX_OLLAMA_MODEL"]),
                    ExtractiveAnswerSynthesizer(),
                )
                if os.environ.get("APRENDIX_OLLAMA_MODEL")
                else ExtractiveAnswerSynthesizer()
            ),
            curated=knowledge_structure,
        ),
        corrector=corrector,
        desktop=desktop,
        cluster_service=HdbscanClusterService(knowledge_repository),
        cache=cache,
        sync_queue=EncryptedSyncQueue(cache),
        curriculum=curriculum,
        knowledge_structure=knowledge_structure,
    )


def _snapshot(runtime: Runtime) -> dict[str, Any]:
    return runtime.graph_snapshot_service.get_snapshot(
        runtime.user.id
    ).model_dump(mode="json", exclude_computed_fields=True)


def main() -> int:
    runtime = build_runtime()
    return run_cli(
        user=runtime.user,
        exercises=runtime.exercises,
        events=runtime.event_service,
        submissions=runtime.submission_service,
    )


def gui_main() -> int:
    runtime = build_runtime()
    controller = LearningGuiController(
        user=runtime.user,
        exercises=runtime.exercises,
        submissions=runtime.submission_service,
        snapshot_provider=lambda: _snapshot(runtime),
        search_service=runtime.search_service,
        card_provider=lambda **filters: runtime.knowledge.list_theory_cards(limit=60, authored_only=True, **filters),
        corrector=runtime.corrector,
        desktop=runtime.desktop,
        cluster_provider=lambda: runtime.knowledge.list_clusters(limit=40),
        curriculum=runtime.curriculum,
        knowledge_structure=runtime.knowledge_structure,
    )
    try:
        return launch_kivy(controller)
    except GuiDependencyError:
        return run_cli(
            user=runtime.user,
            exercises=runtime.exercises,
            events=runtime.event_service,
            submissions=runtime.submission_service,
        )


def toga_main() -> int:
    from aprendix.presentation.toga_gui import launch_toga

    runtime = build_runtime()
    return launch_toga(
        LearningGuiController(
            user=runtime.user,
            exercises=runtime.exercises,
            submissions=runtime.submission_service,
            snapshot_provider=lambda: _snapshot(runtime),
            search_service=runtime.search_service,
            card_provider=lambda **filters: runtime.knowledge.list_theory_cards(limit=60, authored_only=True, **filters),
            corrector=runtime.corrector,
            desktop=runtime.desktop,
            cluster_provider=lambda: runtime.knowledge.list_clusters(limit=40),
            curriculum=runtime.curriculum,
            knowledge_structure=runtime.knowledge_structure,
        )
    )
