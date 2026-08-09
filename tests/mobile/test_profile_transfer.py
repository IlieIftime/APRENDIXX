from pathlib import Path

import pytest

from aprendix.application.profile_transfer import LEGACY_MAGIC, ProfileTransferError, read_profile
from aprendix_mobile.paths import PlatformPaths
from aprendix_mobile.runtime import build_mobile_runtime
from aprendix_mobile.seed import build_seed


def _runtime(root: Path):
    assets = root / "assets"; assets.mkdir(parents=True)
    build_seed(assets / "knowledge-lite.db", assets / "seed-manifest.json")
    paths = PlatformPaths.resolve(
        user_data_dir=root / "data", cache_dir=root / "cache", resources_dir=assets,
    )
    return build_mobile_runtime(paths, allow_host_development=True)


def test_encrypted_profile_roundtrip_and_conflict_preview(tmp_path: Path) -> None:
    source = _runtime(tmp_path / "source")
    source.state.record_card("python-output", "known")
    source.state.complete_unit("python-foundations-values")
    source.execute("hello", "print('segredo-portátil')", "segredo-portátil")
    source.save_project("Projeto móvel", "SEGREDO_PROJETO_MOVEL = 7")
    package = source.export_profile(tmp_path / "perfil.apxprofile", "frase-passe-segura")
    assert b"segredo-port" not in package.read_bytes()

    target = _runtime(tmp_path / "target")
    preview = target.preview_profile(package, "frase-passe-segura")
    assert preview == {
        "incoming_reviews": 1, "incoming_attempts": 1,
        "incoming_completed_units": 1, "incoming_projects": 1, "conflicts": 0,
    }
    result = target.import_profile(package, "frase-passe-segura")
    assert result["attempts"] == 1 and target.state.passed_attempts() == 1
    assert target.state.completed_units() == ("python-foundations-values",)
    assert target.projects()[0]["source"] == "SEGREDO_PROJETO_MOVEL = 7"
    assert b"SEGREDO_PROJETO_MOVEL" not in target.state.path.read_bytes()


def test_profile_rejects_wrong_password_and_tampering(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path / "source")
    package = runtime.export_profile(tmp_path / "perfil.apxprofile", "frase-passe-segura")
    with pytest.raises(ProfileTransferError):
        read_profile(package, "palavra-passe-errada")
    payload = bytearray(package.read_bytes()); payload[-1] ^= 1; package.write_bytes(payload)
    with pytest.raises(ProfileTransferError):
        read_profile(package, "frase-passe-segura")


def test_desktop_can_read_legacy_scrypt_profile(tmp_path: Path) -> None:
    import json
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

    salt, nonce = b"s" * 16, b"n" * 12
    key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(b"frase-passe-segura")
    payload = json.dumps({
        "format": 1, "exported_at": "2026-01-01T00:00:00+00:00",
        "snapshot": {"platform": "desktop", "reviews": [], "attempts": [], "completed_units": []},
    }).encode()
    path = tmp_path / "legacy.apxprofile"
    path.write_bytes(LEGACY_MAGIC + salt + nonce + AESGCM(key).encrypt(nonce, payload, LEGACY_MAGIC))
    assert read_profile(path, "frase-passe-segura")["platform"] == "desktop"
