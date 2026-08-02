"""Tests for authenticated encryption and local key handling."""

from pathlib import Path

import pytest

from aprendix.infrastructure.security import AesGcmFieldCipher, FileKeyStore
from aprendix.infrastructure.security.field_cipher import EncryptionError


def test_cipher_round_trip_and_random_nonce() -> None:
    cipher = AesGcmFieldCipher(b"\x01" * 32)
    context = b"attempts.source_code:abc"

    first = cipher.encrypt(b"print('private')", associated_data=context)
    second = cipher.encrypt(b"print('private')", associated_data=context)

    assert first != second
    assert cipher.decrypt(first, associated_data=context) == b"print('private')"
    assert b"private" not in first


def test_cipher_rejects_tampering_and_wrong_context() -> None:
    cipher = AesGcmFieldCipher(b"\x02" * 32)
    encrypted = cipher.encrypt(b"secret", associated_data=b"right-row")
    tampered = encrypted[:-1] + bytes([encrypted[-1] ^ 1])

    with pytest.raises(EncryptionError, match="authentication"):
        cipher.decrypt(tampered, associated_data=b"right-row")
    with pytest.raises(EncryptionError, match="authentication"):
        cipher.decrypt(encrypted, associated_data=b"wrong-row")


def test_file_key_store_creates_and_reuses_256_bit_key(tmp_path: Path) -> None:
    key_path = tmp_path / "keys" / "database.key"
    store = FileKeyStore(key_path)

    first = store.get_or_create_key()
    second = store.get_or_create_key()

    assert len(first) == 32
    assert first == second
    assert key_path.read_bytes() == first


def test_file_key_store_rejects_corrupt_key(tmp_path: Path) -> None:
    key_path = tmp_path / "database.key"
    key_path.write_bytes(b"too-short")

    with pytest.raises(EncryptionError, match="32 bytes"):
        FileKeyStore(key_path).get_or_create_key()

