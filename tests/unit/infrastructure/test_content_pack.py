import json
import zipfile

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aprendix.infrastructure.content_pack import (
    ApxPackVerifier, ContentPackError, ContentPackManager, build_pack,
)


def _manifest(version="1.0.0"):
    return {"format": 1, "pack_id": "python-weekly", "version": version,
            "requires": [], "license": "PSF documentation licence",
            "provenance": "docs.python.org allowlisted adapter"}


def test_signed_pack_installs_atomically_and_rolls_back(tmp_path) -> None:
    key = Ed25519PrivateKey.generate(); verifier = ApxPackVerifier((key.public_key(),))
    manager = ContentPackManager(tmp_path / "packs", verifier)
    first = build_pack(tmp_path / "v1.apxpack", _manifest(), {"content/update.md": b"safe content"}, key)
    verified = manager.install(first, validate_staging=lambda path, _pack: (path / "content/update.md").read_bytes())
    assert verified.file_count == 1
    second = build_pack(tmp_path / "v2.apxpack", _manifest("1.1.0"), {"content/update.md": b"new content"}, key)
    manager.install(second, validate_staging=lambda *_: None)
    manager.rollback("python-weekly", "1.0.0")
    active = json.loads((tmp_path / "packs/python-weekly/active.json").read_text())
    assert active["version"] == "1.0.0"


def test_tampered_traversal_and_interrupted_pack_are_rejected(tmp_path) -> None:
    key = Ed25519PrivateKey.generate(); verifier = ApxPackVerifier((key.public_key(),))
    bad = build_pack(tmp_path / "bad.apxpack", _manifest(), {"../escape.txt": b"escape"}, key)
    with pytest.raises(ContentPackError): verifier.verify(bad)

    pack = build_pack(tmp_path / "valid.apxpack", _manifest(), {"content/safe.txt": b"safe"}, key)
    with zipfile.ZipFile(pack, "a") as archive:
        archive.writestr("content/safe.txt", b"tampered")
    with pytest.raises(ContentPackError): verifier.verify(pack)

    clean = build_pack(tmp_path / "clean.apxpack", _manifest(), {"content/safe.txt": b"safe"}, key)
    manager = ContentPackManager(tmp_path / "packs", verifier)
    with pytest.raises(RuntimeError):
        manager.install(clean, validate_staging=lambda *_: (_ for _ in ()).throw(RuntimeError("editorial gate")))
    assert not (tmp_path / "packs/python-weekly/active.json").exists()


def test_pack_manager_lists_versions_and_rejects_rollback_traversal(tmp_path) -> None:
    key = Ed25519PrivateKey.generate(); manager = ContentPackManager(
        tmp_path / "packs", ApxPackVerifier((key.public_key(),))
    )
    pack = build_pack(
        tmp_path / "valid.apxpack", _manifest(),
        {"content/catalog.json": b'{"version":1}'}, key,
    )
    manager.install(pack, validate_staging=manager.validate_declarative_staging)
    assert manager.installed() == ({
        "pack_id": "python-weekly", "active": "1.0.0", "versions": ("1.0.0",),
    },)
    with pytest.raises(ContentPackError):
        manager.rollback("../escape", "1.0.0")


def test_pack_rejects_invalid_declarative_json_before_activation(tmp_path) -> None:
    key = Ed25519PrivateKey.generate(); manager = ContentPackManager(
        tmp_path / "packs", ApxPackVerifier((key.public_key(),))
    )
    pack = build_pack(
        tmp_path / "invalid-json.apxpack", _manifest(),
        {"content/catalog.json": b"{broken"}, key,
    )
    with pytest.raises(ContentPackError):
        manager.install(pack, validate_staging=manager.validate_declarative_staging)
    assert manager.installed() == ()
