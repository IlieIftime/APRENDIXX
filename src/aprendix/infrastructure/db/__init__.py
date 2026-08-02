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

__all__ = [
    "AttemptRepository",
    "BaseSQLiteRepository",
    "Database",
    "DatabaseConfig",
    "EventRepository",
    "DesktopRepository",
    "ExerciseRepository",
    "LearningRecordRepository",
    "IndexedChunk",
    "IndexedDocument",
    "KnowledgeRepository",
    "KnowledgeStructureRepository",
    "SQLiteGraphRepository",
    "UserRepository",
]
