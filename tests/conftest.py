"""Reusable Sprint 1 infrastructure fixtures."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from aprendix.infrastructure.db import Database, DatabaseConfig
from aprendix.infrastructure.security import AesGcmFieldCipher


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    db = Database(DatabaseConfig(tmp_path / "aprendix-test.db"))
    db.initialize()
    yield db


@pytest.fixture
def cipher() -> AesGcmFieldCipher:
    return AesGcmFieldCipher(b"\x07" * 32)

