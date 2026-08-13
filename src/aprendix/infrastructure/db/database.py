"""Safe SQLite lifecycle and transaction management."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from aprendix.infrastructure.db.schema import MIGRATIONS, SCHEMA_VERSION


class DatabaseError(RuntimeError):
    """Wrap persistence failures that should not leak driver internals."""


class DatabaseSchemaTooNewError(DatabaseError):
    """Raised when the on-disk profile was migrated by a newer app build."""

    def __init__(self, *, unknown_versions: tuple[int, ...], supported_version: int) -> None:
        self.unknown_versions = unknown_versions
        self.supported_version = supported_version
        super().__init__(
            "database schema is newer than this application: "
            f"{list(unknown_versions)}"
        )


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    path: Path
    timeout_seconds: float = 5.0

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        object.__setattr__(self, "path", self.path.expanduser().resolve())


class Database:
    """Own connections, schema upgrades, and nested-safe transactions."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config

    @property
    def path(self) -> Path:
        return self._config.path

    def connect(self, *, write_capable: bool = True) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            self.path,
            timeout=self._config.timeout_seconds,
            isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA trusted_schema = OFF")
        connection.execute("PRAGMA temp_store = MEMORY")
        connection.execute(
            f"PRAGMA busy_timeout = {int(self._config.timeout_seconds * 1000)}"
        )
        # journal_mode and secure_delete are persistent database settings and
        # need not be renegotiated for every short-lived reader.  Avoiding
        # those write-oriented PRAGMAs keeps interactive FTS reads bounded,
        # especially when the profile lives in a synchronized folder.
        if write_capable:
            connection.execute("PRAGMA secure_delete = ON")
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
        return connection

    def initialize(self) -> None:
        """Apply every unapplied migration exactly once."""

        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY NOT NULL,
                        applied_at TEXT NOT NULL
                            DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
                    )
                    """
                )
                rows = connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                ).fetchall()
                applied = {int(row["version"]) for row in rows}
                unknown = {version for version in applied if version > SCHEMA_VERSION}
                if unknown:
                    raise DatabaseSchemaTooNewError(
                        unknown_versions=tuple(sorted(unknown)),
                        supported_version=SCHEMA_VERSION,
                    )
                for version in sorted(MIGRATIONS):
                    if version in applied:
                        continue
                    for statement in MIGRATIONS[version]:
                        connection.execute(statement)
                    connection.execute(
                        "INSERT INTO schema_migrations(version) VALUES (?)",
                        (version,),
                    )
                connection.commit()
            except Exception:
                connection.rollback()
                raise
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Commit all operations atomically or roll them back on any error."""

        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @contextmanager
    def read_connection(self) -> Iterator[sqlite3.Connection]:
        connection = self.connect(write_capable=False)
        try:
            yield connection
        finally:
            connection.close()
