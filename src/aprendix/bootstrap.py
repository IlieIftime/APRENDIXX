"""Composition root that wires application, infrastructure, and presentation."""

from __future__ import annotations

import os
import sys
import time
from importlib.resources import files
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
from aprendix.application.tutor import OfflineTutorService
from aprendix.application.portfolio import ProjectPortfolioService
from aprendix.application.snippet_analysis import SnippetAnalyzer
from aprendix.application.snippet_service import SnippetAssistantService
from aprendix.application.game_service import GameBreakService
from aprendix.application.desktop import DesktopLearningService
from aprendix.application.curriculum import CurriculumService
from aprendix.application.platform import PlatformService
from aprendix.application.progress import LearningProgressService
from aprendix.application.content_governance import ContentGovernanceService
from aprendix.application.content_updates import ContentUpdateService
from aprendix.application.profile_service import ProfileTransferService
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
    PlatformRepository,
    LearningProgressRepository,
    ContentGovernanceRepository,
    TutorRepository,
    PortfolioRepository,
    SnippetRepository,
    GameRepository,
    DesktopProfileRepository,
)
from aprendix.infrastructure.db.schema import SCHEMA_VERSION
from aprendix.infrastructure.curriculum import CurriculumRepository
from aprendix.infrastructure.grading import IsolatedGradingExecutor, OopGradingPolicy
from aprendix.infrastructure.debugger import IsolatedPythonDebugger
from aprendix.infrastructure.image_ocr import LocalImageOcr
from aprendix.infrastructure.content_pack import ApxPackVerifier, ContentPackManager
from aprendix.infrastructure.pack_catalog import PackCatalogImporter
from cryptography.hazmat.primitives.serialization import load_pem_public_key
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
    platform: PlatformService
    progress: LearningProgressService
    content: ContentGovernanceService
    tutor: OfflineTutorService
    portfolio: ProjectPortfolioService
    snippets: SnippetAssistantService
    games: GameBreakService
    content_packs: ContentPackManager
    content_updates: ContentUpdateService
    profile_transfer: ProfileTransferService


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

    build_started = time.perf_counter()
    data_directory = data_directory or default_data_directory()
    database = Database(DatabaseConfig(data_directory / "aprendix.db"))
    database.initialize()
    cipher = AesGcmFieldCipher.from_key_store(
        FileKeyStore(data_directory / "keys" / "fields.key")
    )
    platform_repository = PlatformRepository(database, cipher)
    platform_repository.seed_feature_flags()
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
    content_governance_repository = ContentGovernanceRepository(database, cipher)
    content = ContentGovernanceService(
        content_governance_repository,
        on_content_changed=knowledge_repository.invalidate_cache,
    )
    content.initialize()
    knowledge_repository.audit_content_quality()
    knowledge_repository.rebuild_public_fts()
    knowledge_repository.rebuild_private_search_index()
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
    content.refresh_objective_evidence()
    content.refresh_coverage()
    with database.read_connection() as connection:
        chunk_count = int(connection.execute("SELECT count(*) FROM document_chunks").fetchone()[0])
        bibliography_count = int(connection.execute("SELECT count(*) FROM bibliography_links").fetchone()[0])
    if chunk_count and not bibliography_count:
        curriculum_repository.rebuild_bibliography_links()
    cache = EncryptedOfflineCache(data_directory / "cache", cipher)
    sandbox = PythonSandbox(PythonAstPolicy(allow_classes=True))
    progress = LearningProgressService(LearningProgressRepository(database))
    progress.backfill_legacy_history(user.id)
    desktop = DesktopLearningService(
        user=user, exercises=exercise_repository, submissions=submission_service,
        attempts=attempt_repository, events=event_service,
        workspace=desktop_repository,
        sandbox=sandbox,
        corrector=corrector,
        cache=cache,
        progress=progress,
        debugger=IsolatedPythonDebugger(PythonAstPolicy(allow_classes=True)),
    )
    curriculum = CurriculumService(
        user=user, repository=curriculum_repository, events=event_service,
        web=SafeDuckDuckGoSearch(timeout_seconds=4.0),
        progress=progress,
    )
    platform = PlatformService(
        repository=platform_repository, database=database,
        data_directory=data_directory, expected_schema_version=SCHEMA_VERSION,
        sandbox_runner=sandbox.run,
    )
    platform.record_metric(
        "runtime.startup", (time.perf_counter() - build_started) * 1000, "ms",
        context={"schema_version": SCHEMA_VERSION, "mode": "runtime"},
    )
    search_service = HybridSearchService(
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
    )
    tutor = OfflineTutorService(
        user=user, search=search_service,
        repository=TutorRepository(database, cipher), cache=cache,
    )
    portfolio_repository = PortfolioRepository(database, cipher)
    portfolio_repository.seed()
    portfolio = ProjectPortfolioService(
        user=user, repository=portfolio_repository, desktop=desktop,
    )
    snippets = SnippetAssistantService(
        user=user, analyzer=SnippetAnalyzer(), ocr=LocalImageOcr(),
        repository=SnippetRepository(database, cipher),
    )
    games = GameBreakService(user=user, repository=GameRepository(database, cipher))
    pack_key = load_pem_public_key(
        files("aprendix.presentation").joinpath("assets/pack-public-key.pem").read_bytes()
    )

    def refresh_pack_content() -> None:
        knowledge_structure.ensure_mappings(
            knowledge_repository.search_candidates(SearchFiltersDTO(), limit=100_000)
        )
        curriculum_repository.rebuild_bibliography_links()
        content.refresh_objective_evidence()
        content.refresh_coverage()

    pack_catalog = PackCatalogImporter(
        database, knowledge_repository, content_governance_repository,
        on_changed=refresh_pack_content,
    )
    content_packs = ContentPackManager(
        data_directory / "content-packs", ApxPackVerifier((pack_key,)),
        activator=pack_catalog,
    )
    content_updates = ContentUpdateService(content_packs)
    profile_transfer = ProfileTransferService(
        user.id, DesktopProfileRepository(database, attempt_repository, desktop)
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
        search_service=search_service,
        corrector=corrector,
        desktop=desktop,
        cluster_service=HdbscanClusterService(knowledge_repository),
        cache=cache,
        sync_queue=EncryptedSyncQueue(cache),
        curriculum=curriculum,
        knowledge_structure=knowledge_structure,
        platform=platform,
        progress=progress,
        content=content,
        tutor=tutor,
        portfolio=portfolio,
        snippets=snippets,
        games=games,
        content_packs=content_packs,
        content_updates=content_updates,
        profile_transfer=profile_transfer,
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
        card_provider=lambda **filters: runtime.knowledge.list_theory_cards(limit=60, **filters),
        corrector=runtime.corrector,
        desktop=runtime.desktop,
        cluster_provider=lambda: runtime.knowledge.list_clusters(limit=40),
        curriculum=runtime.curriculum,
        knowledge_structure=runtime.knowledge_structure,
        progress=runtime.progress,
        tutor=runtime.tutor,
        portfolio=runtime.portfolio,
        snippets=runtime.snippets,
        games=runtime.games,
        content_updates=runtime.content_updates,
        profile_transfer=runtime.profile_transfer,
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
            card_provider=lambda **filters: runtime.knowledge.list_theory_cards(limit=60, **filters),
            corrector=runtime.corrector,
            desktop=runtime.desktop,
            cluster_provider=lambda: runtime.knowledge.list_clusters(limit=40),
            curriculum=runtime.curriculum,
            knowledge_structure=runtime.knowledge_structure,
            progress=runtime.progress,
            tutor=runtime.tutor,
            portfolio=runtime.portfolio,
            snippets=runtime.snippets,
            games=runtime.games,
            content_updates=runtime.content_updates,
            profile_transfer=runtime.profile_transfer,
        )
    )
