"""Privacy-preserving metadata synchronization contracts and merge policy."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from aprendix.application.contracts.models import utc_now

HexDigest = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]


class SyncMetadata(BaseModel):
    """Sync-safe metadata; raw source, output, prompts, and PII are forbidden."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity_type: Annotated[
        str,
        StringConstraints(pattern=r"^[a-z][a-z0-9_.-]{0,63}$"),
    ]
    entity_id: UUID
    revision: int = Field(ge=1)
    changed_at: datetime = Field(default_factory=utc_now)
    content_digest: HexDigest
    origin_device_id: UUID
    tombstone: bool = False


class SyncBatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=utc_now)
    items: tuple[SyncMetadata, ...] = Field(max_length=500)


class MergeResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    merged: tuple[SyncMetadata, ...]
    conflicts: tuple[str, ...]


class MetadataSyncEngine:
    """Deterministically merge revisioned metadata from offline devices."""

    @staticmethod
    def merge(
        local: tuple[SyncMetadata, ...],
        remote: tuple[SyncMetadata, ...],
    ) -> MergeResult:
        selected: dict[tuple[str, UUID], SyncMetadata] = {}
        conflicts: list[str] = []

        for candidate in (*local, *remote):
            key = (candidate.entity_type, candidate.entity_id)
            current = selected.get(key)
            if current is None:
                selected[key] = candidate
                continue
            if (
                candidate.revision == current.revision
                and candidate.content_digest != current.content_digest
            ):
                conflicts.append(f"{candidate.entity_type}:{candidate.entity_id}")
            selected[key] = max(
                (current, candidate),
                key=lambda item: (
                    item.revision,
                    item.changed_at,
                    str(item.origin_device_id),
                ),
            )

        ordered = tuple(
            selected[key]
            for key in sorted(selected, key=lambda item: (item[0], str(item[1])))
        )
        return MergeResult(
            merged=ordered,
            conflicts=tuple(sorted(set(conflicts))),
        )

