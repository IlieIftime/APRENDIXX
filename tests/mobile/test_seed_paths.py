import json
from pathlib import Path

import pytest

from aprendix_mobile.paths import PlatformPaths
from aprendix_mobile.seed import LiteContentStore, SeedManifest, build_seed, install_seed


def test_platform_paths_are_injected_and_private(tmp_path: Path) -> None:
    paths = PlatformPaths.resolve(
        user_data_dir=tmp_path / "data", cache_dir=tmp_path / "cache",
        resources_dir=tmp_path / "assets",
    )
    assert paths.user_database.parent == (tmp_path / "data").resolve()
    assert paths.durable_queue.parent.name == "state"
    assert paths.cache != paths.data


def test_seed_build_install_readonly_and_idempotent(tmp_path: Path) -> None:
    asset, manifest_file = tmp_path / "asset.db", tmp_path / "manifest.json"
    manifest = build_seed(asset, manifest_file)
    assert asset.stat().st_size < 200 * 1024 * 1024
    assert SeedManifest.load(manifest_file) == manifest
    destination = tmp_path / "private" / "content.db"
    assert install_seed(asset, manifest, destination) is True
    assert install_seed(asset, manifest, destination) is False
    cards = LiteContentStore(destination).cards(theme="oop")
    assert len(cards) == 1
    assert cards[0]["id"] == "python-objects"
    assert cards[0]["exercise_id"] == "exercise-python-objects"
    assert cards[0]["expected_output"] == "2"
    assert len(cards[0]["options"]) == 3
    glossary = LiteContentStore(destination).glossary("pri")
    assert glossary[0]["term"] == "print"
    assert LiteContentStore(destination).glossary("virtualenv")[0]["term"] == "virtual environment"


def test_seed_tampering_fails_closed_without_replacing_destination(tmp_path: Path) -> None:
    asset, manifest_file = tmp_path / "asset.db", tmp_path / "manifest.json"
    manifest = build_seed(asset, manifest_file)
    payload = bytearray(asset.read_bytes()); payload[-1] ^= 1; asset.write_bytes(payload)
    destination = tmp_path / "content.db"
    with pytest.raises(ValueError):
        install_seed(asset, manifest, destination)
    assert not destination.exists()
