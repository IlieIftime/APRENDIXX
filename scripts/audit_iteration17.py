"""Offline acceptance gate for signed weekly desktop content updates."""

from __future__ import annotations

import hashlib
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aprendix.infrastructure.content_pack import (
    ApxPackVerifier,
    ContentPackManager,
    build_pack,
)
from aprendix.infrastructure.update_broker import (
    ConnectivityState,
    ContentUpdateBroker,
    FetchResponse,
    UpdatePolicy,
)


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "ITERATION-17-AUDIT-1.0.0.json"


class _Client:
    registry = b""
    pack = b""
    fetches = 0

    def __init__(self, _hosts: tuple[str, ...]) -> None:
        pass

    def fetch(self, _url: str, *, max_bytes: int, etag: str = "", last_modified: str = ""):
        type(self).fetches += 1
        return FetchResponse(200, self.registry[:max_bytes], '"audit-v1"', "")

    def download(self, _url: str, destination: Path, *, max_bytes: int):
        payload = self.pack[:max_bytes]
        destination.write_bytes(payload)
        return len(payload), hashlib.sha256(payload).hexdigest()


def _registry(payload: bytes) -> bytes:
    now = datetime.now(UTC).isoformat()
    return json.dumps({
        "format": 1,
        "generated_at": now,
        "packs": [{
            "pack_id": "python-official",
            "version": "1.0.0",
            "title": "Documentação Python validada",
            "summary": "Atualização declarativa de conteúdo oficial.",
            "url": "https://updates.aprendix.test/python-official-1.0.0.apxpack",
            "sha256": hashlib.sha256(payload).hexdigest(),
            "size": len(payload),
            "published_at": now,
            "sources": ["https://docs.python.org/3/"],
            "affected_tracks": ["python-foundations"],
            "channel": "stable",
        }],
    }, separators=(",", ":")).encode("utf-8")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aprendix-iteration17-") as directory:
        root = Path(directory)
        key = Ed25519PrivateKey.generate()
        pack = build_pack(
            root / "official.apxpack",
            {
                "format": 1,
                "pack_id": "python-official",
                "version": "1.0.0",
                "requires": [],
                "license": "PSF-2.0",
                "provenance": "https://docs.python.org/3/",
            },
            {"content/index.json": b'{"items":[]}'},
            key,
        )
        _Client.pack = pack.read_bytes()
        _Client.registry = _registry(_Client.pack)
        _Client.fetches = 0
        manager = ContentPackManager(root / "packs", ApxPackVerifier((key.public_key(),)))
        broker = ContentUpdateBroker(manager, client_factory=_Client)
        policy = UpdatePolicy(
            enabled=True,
            registry_url="https://updates.aprendix.test/registry.json",
            allowed_hosts=("updates.aprendix.test",),
            interval_days=7,
            wifi_only=True,
        )
        deferred = broker.check(
            policy, connectivity=ConnectivityState(unmetered=False), force=True
        )
        checked = broker.check(
            policy, connectivity=ConnectivityState(unmetered=True), force=True
        )
        offer = checked["offers"][0]
        preview = broker.preview(offer, policy)
        installed = broker.install(offer, policy)
        cached = broker.check(policy, connectivity=ConnectivityState(unmetered=True))
        checks = {
            "opt_in_and_connectivity_policy": deferred["status"] == "deferred",
            "https_host_allowlist": offer.url.startswith("https://updates.aprendix.test/"),
            "explicit_preview": (
                preview["requires_confirmation"] is True
                and preview["uploads_user_data"] is False
                and preview["sources"] == ("https://docs.python.org/3/",)
            ),
            "signature_hash_and_staging_validated": (
                installed["version"] == "1.0.0"
                and manager.installed()[0]["active"] == "1.0.0"
            ),
            "weekly_cache_prevents_repeat_network": (
                cached["status"] == "cached" and _Client.fetches == 1
            ),
        }
        report = {
            "iteration": 17,
            "passed": all(checks.values()),
            "checks": checks,
            "metrics": {
                "interval_days": policy.interval_days,
                "registry_fetches": _Client.fetches,
                "installed_files": installed["file_count"],
                "installed_bytes": installed["total_bytes"],
            },
            "privacy": "offline synthetic pack; no learner data or external request",
        }
        OUTPUT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
