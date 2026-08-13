"""SQLite connection, schema, and repositories."""

from aprendix.infrastructure.db.database import Database, DatabaseConfig
from aprendix.infrastructure.db.graph_repository import SQLiteGraphRepository
from aprendix.infrastructure.db.repositories import (
    AttemptRepository,
    BaseSQLiteRepository,
    EventRepository,
    ExerciseRepository,
    LearningRecordRepository,
    UserRepository,
)
from aprendix.infrastructure.db.knowledge_repository import (
    IndexedChunk,
    IndexedDocument,
    KnowledgeRepository,
)
from aprendix.infrastructure.db.desktop_repository import DesktopRepository
from aprendix.infrastructure.db.knowledge_structure_repository import KnowledgeStructureRepository
from aprendix.infrastructure.db.platform_repository import PlatformRepository
from aprendix.infrastructure.db.progress_repository import LearningProgressRepository
from aprendix.infrastructure.db.content_governance_repository import ContentGovernanceRepository
from aprendix.infrastructure.db.tutor_repository import TutorRepository
from aprendix.infrastructure.db.portfolio_repository import PortfolioRepository
from aprendix.infrastructure.db.snippet_repository import SnippetRepository
from aprendix.infrastructure.db.game_repository import GameRepository
from aprendix.infrastructure.db.profile_repository import DesktopProfileRepository
from aprendix.infrastructure.db.quality_repository import PedagogicalQualityRepository
from aprendix.infrastructure.db.pedagogical_repository import (
    CatalogSearchHit,
    PedagogicalRepository,
)
from aprendix.infrastructure.db.catalog_repository import EditorialCatalogRepository

__all__ = [
    "AttemptRepository",
    "BaseSQLiteRepository",
    "ContentGovernanceRepository",
    "Database",
    "DatabaseConfig",
    "EventRepository",
    "DesktopRepository",
    "ExerciseRepository",
    "LearningRecordRepository",
    "LearningProgressRepository",
    "IndexedChunk",
    "IndexedDocument",
    "KnowledgeRepository",
    "KnowledgeStructureRepository",
    "PlatformRepository",
    "SQLiteGraphRepository",
    "UserRepository",
    "TutorRepository",
    "PortfolioRepository",
    "SnippetRepository",
    "GameRepository",
    "DesktopProfileRepository",
    "PedagogicalQualityRepository",
    "CatalogSearchHit",
    "PedagogicalRepository",
    "EditorialCatalogRepository",
]
