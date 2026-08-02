"""Encrypted bounded offline cache with authenticated index metadata."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from aprendix.infrastructure.security import AesGcmFieldCipher


class CacheCapacityError(ValueError):
    """Raised when one value cannot fit inside the configured cache."""


class EncryptedOfflineCache:
    """Store cache values and their index encrypted, evicting least-recently used."""

    def __init__(
        self,
        directory: Path,
        cipher: AesGcmFieldCipher,
        *,
        max_bytes: int = 8 * 1024 * 1024,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self._directory = directory.expanduser().resolve()
        self._directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        self._cipher = cipher
        self._max_bytes = max_bytes
        self._clock = clock
        self._lock = threading.RLock()
        self._index_path = self._directory / "index.enc"

    @staticmethod
    def _digest(key: str) -> str:
        if not key:
            raise ValueError("cache key cannot be empty")
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def put(self, key: str, value: bytes, *, ttl_seconds: float | None = None) -> None:
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        digest = self._digest(key)
        envelope = self._cipher.encrypt(
            value,
            associated_data=f"cache.entry:{digest}".encode(),
        )
        if len(envelope) > self._max_bytes:
            raise CacheCapacityError("value exceeds total cache capacity")

        with self._lock:
            index = self._load_index()
            now = self._clock()
            path = self._directory / f"{digest}.bin"
            self._atomic_write(path, envelope)
            index[digest] = {
                "size": len(envelope),
                "accessed_at": now,
                "expires_at": now + ttl_seconds if ttl_seconds is not None else None,
            }
            self._evict(index, protected=digest)
            self._save_index(index)

    def get(self, key: str) -> bytes | None:
        digest = self._digest(key)
        with self._lock:
            index = self._load_index()
            record = index.get(digest)
            if record is None:
                return None
            expires_at = record["expires_at"]
            if expires_at is not None and self._clock() >= float(expires_at):
                self._remove_entry(index, digest)
                self._save_index(index)
                return None
            path = self._directory / f"{digest}.bin"
            if not path.exists():
                index.pop(digest, None)
                self._save_index(index)
                return None
            plaintext = self._cipher.decrypt(
                path.read_bytes(),
                associated_data=f"cache.entry:{digest}".encode(),
            )
            record["accessed_at"] = self._clock()
            self._save_index(index)
            return plaintext

    def delete(self, key: str) -> bool:
        digest = self._digest(key)
        with self._lock:
            index = self._load_index()
            if digest not in index:
                return False
            self._remove_entry(index, digest)
            self._save_index(index)
            return True

    def _evict(self, index: dict[str, dict[str, Any]], *, protected: str) -> None:
        while sum(int(record["size"]) for record in index.values()) > self._max_bytes:
            candidates = [digest for digest in index if digest != protected]
            if not candidates:
                raise CacheCapacityError("protected value cannot fit in cache")
            oldest = min(
                candidates,
                key=lambda digest: (float(index[digest]["accessed_at"]), digest),
            )
            self._remove_entry(index, oldest)

    def _remove_entry(self, index: dict[str, dict[str, Any]], digest: str) -> None:
        index.pop(digest, None)
        path = self._directory / f"{digest}.bin"
        if path.exists():
            path.unlink()

    def _load_index(self) -> dict[str, dict[str, Any]]:
        if not self._index_path.exists():
            return {}
        plaintext = self._cipher.decrypt(
            self._index_path.read_bytes(),
            associated_data=b"cache.index:v1",
        )
        decoded = json.loads(plaintext)
        if not isinstance(decoded, dict):
            raise ValueError("cache index must contain a JSON object")
        return decoded

    def _save_index(self, index: dict[str, dict[str, Any]]) -> None:
        plaintext = json.dumps(
            index,
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        envelope = self._cipher.encrypt(
            plaintext,
            associated_data=b"cache.index:v1",
        )
        self._atomic_write(self._index_path, envelope)

    @staticmethod
    def _atomic_write(path: Path, content: bytes) -> None:
        descriptor, temporary_name = tempfile.mkstemp(
            dir=path.parent,
            prefix=f".{path.name}.",
        )
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, path)
            path.chmod(0o600)
        finally:
            if temporary.exists():
                temporary.unlink()

