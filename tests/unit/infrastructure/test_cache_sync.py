"""Encrypted cache and durable metadata queue tests."""

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from aprendix.application.sync import SyncMetadata
from aprendix.infrastructure.cache import EncryptedOfflineCache
from aprendix.infrastructure.security import AesGcmFieldCipher
from aprendix.infrastructure.sync import EncryptedSyncQueue


def test_cache_round_trip_expiry_and_encrypted_disk(
    tmp_path: Path,
    cipher: AesGcmFieldCipher,
) -> None:
    now = [100.0]
    cache = EncryptedOfflineCache(
        tmp_path / "cache",
        cipher,
        max_bytes=1024,
        clock=lambda: now[0],
    )

    cache.put("lesson:1", b"sensitive cached value", ttl_seconds=10)

    assert cache.get("lesson:1") == b"sensitive cached value"
    assert b"sensitive cached value" not in b"".join(
        path.read_bytes() for path in (tmp_path / "cache").iterdir()
    )
    now[0] = 111.0
    assert cache.get("lesson:1") is None


def test_cache_evicts_least_recently_used(
    tmp_path: Path,
    cipher: AesGcmFieldCipher,
) -> None:
    now = [1.0]
    cache = EncryptedOfflineCache(
        tmp_path / "cache",
        cipher,
        max_bytes=90,
        clock=lambda: now[0],
    )
    cache.put("old", b"a" * 30)
    now[0] = 2.0
    cache.put("new", b"b" * 30)

    assert cache.get("old") is None
    assert cache.get("new") == b"b" * 30


def test_sync_queue_is_encrypted_and_acknowledgeable(
    tmp_path: Path,
    cipher: AesGcmFieldCipher,
) -> None:
    cache = EncryptedOfflineCache(tmp_path / "cache", cipher)
    queue = EncryptedSyncQueue(cache)
    metadata = SyncMetadata(
        entity_type="profile.stats",
        entity_id=uuid4(),
        revision=1,
        changed_at=datetime(2026, 1, 1, tzinfo=UTC),
        content_digest="a" * 64,
        origin_device_id=uuid4(),
    )

    queue.enqueue(metadata)

    assert queue.load() == (metadata,)
    disk = b"".join(path.read_bytes() for path in (tmp_path / "cache").iterdir())
    assert str(metadata.entity_id).encode() not in disk
    queue.acknowledge((metadata,))
    assert queue.load() == ()
