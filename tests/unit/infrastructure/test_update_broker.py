from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aprendix.infrastructure.content_pack import ApxPackVerifier, ContentPackManager, build_pack
from aprendix.infrastructure.update_broker import (
    ConnectivityState,
    ContentUpdateBroker,
    FetchResponse,
    RemotePackOffer,
    UpdateBrokerError,
    UpdatePolicy,
    parse_registry,
)


class FakeClient:
    registry = b""
    pack = b""
    fetches = 0

    def __init__(self, _hosts):
        pass

    def fetch(self, _url, *, max_bytes, etag="", last_modified=""):
        type(self).fetches += 1
        assert len(self.registry) <= max_bytes
        return FetchResponse(200, self.registry, '"v1"', "Sun, 09 Aug 2026 10:00:00 GMT")

    def download(self, _url, destination, *, max_bytes):
        assert len(self.pack) <= max_bytes
        destination.write_bytes(self.pack)
        return len(self.pack), hashlib.sha256(self.pack).hexdigest()


def _registry(pack_bytes: bytes, *, digest: str | None = None):
    return json.dumps({
        "format": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "packs": [{
            "pack_id": "python-core", "version": "1.2.0", "title": "Python core",
            "summary": "Novos exercícios revistos.",
            "url": "https://updates.example.test/python-core-1.2.0.apxpack",
            "sha256": digest or hashlib.sha256(pack_bytes).hexdigest(),
            "size": len(pack_bytes), "published_at": datetime.now(UTC).isoformat(),
            "sources": ["docs.python.org"], "affected_tracks": ["python-foundations"],
            "channel": "stable",
        }],
    }, separators=(",", ":")).encode()


def _policy(**changes):
    values = dict(
        enabled=True,
        registry_url="https://updates.example.test/registry.json",
        allowed_hosts=("updates.example.test",),
    )
    values.update(changes)
    return UpdatePolicy(**values)


def test_broker_checks_caches_and_installs_only_signed_pack(tmp_path):
    key = Ed25519PrivateKey.generate()
    pack_path = build_pack(
        tmp_path / "source.apxpack",
        {"format": 1, "pack_id": "python-core", "version": "1.2.0",
         "requires": [], "license": "PSF", "provenance": "docs.python.org"},
        {"content/index.json": b'{"items":[]}'}, key,
    )
    FakeClient.pack = pack_path.read_bytes()
    FakeClient.registry = _registry(FakeClient.pack)
    FakeClient.fetches = 0
    manager = ContentPackManager(tmp_path / "packs", ApxPackVerifier((key.public_key(),)))
    broker = ContentUpdateBroker(manager, client_factory=FakeClient)

    checked = broker.check(_policy(), force=True)
    assert checked["status"] == "checked"
    assert checked["offers"][0].pack_id == "python-core"
    assert broker.check(_policy())["status"] == "cached"
    assert FakeClient.fetches == 1

    installed = broker.install(checked["offers"][0], _policy())
    assert installed["version"] == "1.2.0"
    assert manager.installed()[0]["active"] == "1.2.0"
    assert broker.check(_policy())["offers"] == ()


def test_broker_defers_policy_and_quarantines_bad_download(tmp_path):
    key = Ed25519PrivateKey.generate()
    manager = ContentPackManager(tmp_path / "packs", ApxPackVerifier((key.public_key(),)))
    broker = ContentUpdateBroker(manager, client_factory=FakeClient)
    assert broker.check(
        _policy(wifi_only=True), connectivity=ConnectivityState(unmetered=False), force=True,
    )["status"] == "deferred"

    FakeClient.pack = b"not-a-signed-pack"
    offer = RemotePackOffer(
        "python-core", "1.2.0", "Python core", "Atualização revista.",
        "https://updates.example.test/pack.apxpack",
        hashlib.sha256(FakeClient.pack).hexdigest(), len(FakeClient.pack),
        datetime.now(UTC).isoformat(), ("docs.python.org",), ("python-foundations",),
    )
    with pytest.raises(ValueError):
        broker.install(offer, _policy())
    assert len(tuple((tmp_path / "packs" / ".broker" / "quarantine").glob("*.apxpack"))) == 1
    assert manager.installed() == ()


def test_registry_rejects_cross_host_and_credentials():
    payload = _registry(b"pack")
    value = json.loads(payload)
    value["packs"][0]["url"] = "https://evil.example/pack.apxpack"
    with pytest.raises(UpdateBrokerError):
        parse_registry(json.dumps(value).encode(), allowed_hosts=("updates.example.test",), channel="stable")
    with pytest.raises(UpdateBrokerError):
        UpdatePolicy(True, "https://user:secret@updates.example.test/registry.json", ("updates.example.test",))
