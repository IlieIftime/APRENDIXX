"""Behavior tests for the transactional repository foundation."""

import sqlite3

import pytest

from aprendix.application.contracts import UserDTO
from aprendix.infrastructure.db import Database, UserRepository
from aprendix.infrastructure.db.repositories import EntityNotFoundError
from aprendix.infrastructure.security import AesGcmFieldCipher


def test_user_repository_round_trip_encrypts_sensitive_name(
    database: Database,
    cipher: AesGcmFieldCipher,
) -> None:
    repository = UserRepository(database, cipher)
    user = UserDTO(display_name="Grace Hopper", consent_sync=True)

    repository.add(user)
    restored = repository.get(user.id)

    with database.read_connection() as connection:
        raw_name = connection.execute(
            "SELECT display_name_encrypted FROM users WHERE id = ?",
            (str(user.id),),
        ).fetchone()[0]

    assert restored == user
    assert isinstance(raw_name, bytes)
    assert b"Grace Hopper" not in raw_name


def test_duplicate_user_is_rejected_atomically(
    database: Database,
    cipher: AesGcmFieldCipher,
) -> None:
    repository = UserRepository(database, cipher)
    user = UserDTO(display_name="Linus")
    repository.add(user)

    with pytest.raises(sqlite3.IntegrityError):
        repository.add(user)

    assert repository.get(user.id) == user


def test_delete_reports_presence_and_get_reports_absence(
    database: Database,
    cipher: AesGcmFieldCipher,
) -> None:
    repository = UserRepository(database, cipher)
    user = UserDTO(display_name=None)
    repository.add(user)

    assert repository.delete(user.id) is True
    assert repository.delete(user.id) is False
    with pytest.raises(EntityNotFoundError, match=str(user.id)):
        repository.get(user.id)

