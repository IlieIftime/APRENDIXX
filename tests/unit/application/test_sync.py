"""Metadata-only sync merge tests."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from aprendix.application.sync import MetadataSyncEngine, SyncMetadata


def item(*, revision: int, digest: str, device, entity=None, changed=None):
    return SyncMetadata(
        entity_type="profile.stats",
        entity_id=entity or uuid4(),
        revision=revision,
        changed_at=changed or datetime(2026, 1, 1, tzinfo=UTC),
        content_digest=digest * 64,
        origin_device_id=device,
    )


def test_sync_merge_prefers_revision_and_reports_content_conflict() -> None:
    entity = uuid4()
    device_a = uuid4()
    device_b = uuid4()
    local = item(revision=2, digest="a", device=device_a, entity=entity)
    remote = item(revision=2, digest="b", device=device_b, entity=entity)

    result = MetadataSyncEngine.merge((local,), (remote,))

    assert len(result.merged) == 1
    assert result.conflicts == (f"profile.stats:{entity}",)
    assert result.merged[0].origin_device_id == max(device_a, device_b, key=str)


def test_sync_merge_prefers_newer_revision_without_raw_content() -> None:
    entity = uuid4()
    device = uuid4()
    old = item(revision=1, digest="a", device=device, entity=entity)
    new = item(
        revision=2,
        digest="b",
        device=device,
        entity=entity,
        changed=old.changed_at + timedelta(seconds=1),
    )

    result = MetadataSyncEngine.merge((old,), (new,))

    assert result.merged == (new,)
    assert "source_code" not in new.model_dump()

