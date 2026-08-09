from pathlib import Path

import pytest

from aprendix_mobile.paths import PlatformPaths
from aprendix_mobile.runtime import build_mobile_runtime
from aprendix_mobile.seed import build_seed


def _runtime(root: Path):
    assets = root / "assets"
    assets.mkdir(parents=True)
    build_seed(assets / "knowledge-lite.db", assets / "seed-manifest.json")
    paths = PlatformPaths.resolve(
        user_data_dir=root / "data", cache_dir=root / "cache", resources_dir=assets,
    )
    return build_mobile_runtime(paths, allow_host_development=True)


def test_mobile_projects_are_encrypted_and_reject_traversal(tmp_path):
    runtime = _runtime(tmp_path)
    saved = runtime.save_project(
        "Árvore", "SEGREDO_MOBILE_291 = 1", relative_path="src/arvore.py",
    )
    assert runtime.projects()[0] == saved
    assert b"SEGREDO_MOBILE_291" not in runtime.state.path.read_bytes()
    with pytest.raises(ValueError):
        runtime.save_project("Fora", "x=1", relative_path="../fora.py")


def test_mobile_tutor_is_grounded_and_refuses_unknown_topics(tmp_path):
    runtime = _runtime(tmp_path)
    supported = runtime.ask_tutor("Como funciona print em Python?")
    assert supported["declined"] is False
    assert supported["evidence"]
    unsupported = runtime.ask_tutor("Como reparar um motor de combustão marítimo?")
    assert unsupported["declined"] is True
    assert unsupported["evidence"] == ()
