"""Authenticated field encryption for sensitive SQLite values."""

from __future__ import annotations

import os
import secrets
import hashlib
import hmac
from pathlib import Path
from typing import Protocol, runtime_checkable

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_FORMAT_VERSION = b"\x01"
_NONCE_LENGTH = 12
_KEY_LENGTH = 32


class EncryptionError(ValueError):
    """Raised when encrypted data is malformed or fails authentication."""


@runtime_checkable
class KeyStore(Protocol):
    """Boundary implemented later by Keychain/Keystore platform adapters."""

    def get_or_create_key(self) -> bytes:
        """Return a stable 256-bit key, creating it if needed."""


class FileKeyStore:
    """Persist a random encryption key separately with owner-only permissions."""

    def __init__(self, path: Path) -> None:
        self._path = path.expanduser().resolve()

    @property
    def path(self) -> Path:
        return self._path

    def get_or_create_key(self) -> bytes:
        if self._path.exists():
            key = self._path.read_bytes()
            self._validate_key(key)
            self._restrict_permissions()
            return key

        self._path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        key = secrets.token_bytes(_KEY_LENGTH)
        try:
            descriptor = os.open(
                self._path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            key = self._path.read_bytes()
            self._validate_key(key)
            self._restrict_permissions()
            return key

        with os.fdopen(descriptor, "wb") as key_file:
            key_file.write(key)
            key_file.flush()
            os.fsync(key_file.fileno())
        self._restrict_permissions()
        return key

    def _restrict_permissions(self) -> None:
        try:
            self._path.chmod(0o600)
        except OSError as exc:
            raise EncryptionError(
                f"cannot restrict key-file permissions: {self._path}"
            ) from exc

    @staticmethod
    def _validate_key(key: bytes) -> None:
        if len(key) != _KEY_LENGTH:
            raise EncryptionError("key file must contain exactly 32 bytes")


class AesGcmFieldCipher:
    """Encrypt each value independently using AES-256-GCM.

    Callers should use a stable, record-specific associated-data value such as
    ``b"users.display_name:<uuid>"``. It prevents a valid ciphertext from being
    moved to a different row or column without detection.
    """

    def __init__(self, key: bytes) -> None:
        if len(key) != _KEY_LENGTH:
            raise ValueError("AES-256-GCM requires a 32-byte key")
        self._cipher = AESGCM(key)
        self._blind_key = hmac.new(key, b"aprendix:blind-index:v1", hashlib.sha256).digest()

    @classmethod
    def from_key_store(cls, key_store: KeyStore) -> AesGcmFieldCipher:
        return cls(key_store.get_or_create_key())

    def encrypt(self, plaintext: bytes, *, associated_data: bytes) -> bytes:
        nonce = secrets.token_bytes(_NONCE_LENGTH)
        ciphertext = self._cipher.encrypt(nonce, plaintext, associated_data)
        return _FORMAT_VERSION + nonce + ciphertext

    def decrypt(self, envelope: bytes, *, associated_data: bytes) -> bytes:
        minimum_size = len(_FORMAT_VERSION) + _NONCE_LENGTH + 16
        if len(envelope) < minimum_size or envelope[:1] != _FORMAT_VERSION:
            raise EncryptionError("unsupported or truncated ciphertext")
        nonce = envelope[1 : 1 + _NONCE_LENGTH]
        ciphertext = envelope[1 + _NONCE_LENGTH :]
        try:
            return self._cipher.decrypt(nonce, ciphertext, associated_data)
        except InvalidTag as exc:
            raise EncryptionError("ciphertext authentication failed") from exc

    def blind_index(self, value: bytes, *, namespace: bytes) -> bytes:
        """Create a keyed, deterministic digest suitable for equality indexes.

        The digest cannot be reversed or checked with an offline dictionary
        without the profile key. Namespaces prevent correlation across fields.
        """
        if not namespace or len(namespace) > 120:
            raise ValueError("blind-index namespace must contain 1 to 120 bytes")
        return hmac.new(self._blind_key, namespace + b"\x00" + value, hashlib.sha256).digest()
