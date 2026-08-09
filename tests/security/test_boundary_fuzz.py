"""Deterministic malformed-input sweep over externally reachable parsers."""

from __future__ import annotations

import random

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from aprendix.application.profile_transfer import ProfileTransferError, read_profile
from aprendix.infrastructure.content_pack import ApxPackVerifier, ContentPackError
from aprendix.infrastructure.image_ocr import LocalImageOcr


@pytest.mark.parametrize("seed", range(24))
def test_untrusted_binary_parsers_fail_closed(tmp_path, seed: int) -> None:
    randomizer = random.Random(seed)
    payload = randomizer.randbytes(randomizer.randint(0, 4096))
    profile = tmp_path / f"fuzz-{seed}.apxprofile"
    image = tmp_path / f"fuzz-{seed}.png"
    pack = tmp_path / f"fuzz-{seed}.apxpack"
    profile.write_bytes(payload)
    image.write_bytes(payload)
    pack.write_bytes(payload)

    with pytest.raises((ProfileTransferError, OSError)):
        read_profile(profile, "frase-passe-segura")
    with pytest.raises((ValueError, RuntimeError, OSError)):
        LocalImageOcr().extract(image)
    verifier = ApxPackVerifier((Ed25519PrivateKey.generate().public_key(),))
    with pytest.raises(ContentPackError):
        verifier.verify(pack)
