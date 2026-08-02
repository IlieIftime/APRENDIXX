"""Encrypted durable queue for optional metadata-only synchronization."""

from __future__ import annotations

from pathlib import Path

from aprendix.application.sync import SyncBatch, SyncMetadata
from aprendix.infrastructure.cache import EncryptedOfflineCache


class EncryptedSyncQueue:
    """Persist pending sync metadata through the encrypted offline cache."""

    _QUEUE_KEY = "sync:pending-metadata:v1"

    def __init__(self, cache: EncryptedOfflineCache) -> None:
        self._cache = cache

    def load(self) -> tuple[SyncMetadata, ...]:
        payload = self._cache.get(self._QUEUE_KEY)
        if payload is None:
            return ()
        return SyncBatch.model_validate_json(payload).items

    def enqueue(self, metadata: SyncMetadata) -> None:
        current = {
            (item.entity_type, item.entity_id): item for item in self.load()
        }
        key = (metadata.entity_type, metadata.entity_id)
        existing = current.get(key)
        if existing is None or metadata.revision >= existing.revision:
            current[key] = metadata
        ordered = tuple(
            current[key]
            for key in sorted(current, key=lambda item: (item[0], str(item[1])))
        )
        self._cache.put(
            self._QUEUE_KEY,
            SyncBatch(items=ordered).model_dump_json().encode(),
        )

    def acknowledge(self, batch: tuple[SyncMetadata, ...]) -> None:
        acknowledged = {
            (item.entity_type, item.entity_id, item.revision) for item in batch
        }
        remaining = tuple(
            item
            for item in self.load()
            if (item.entity_type, item.entity_id, item.revision) not in acknowledged
        )
        if remaining:
            self._cache.put(
                self._QUEUE_KEY,
                SyncBatch(items=remaining).model_dump_json().encode(),
            )
        else:
            self._cache.delete(self._QUEUE_KEY)

