"""Platform AES-GCM adapter that avoids shipping a legacy Android OpenSSL stack."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

VERSION = b"\x01"
NONCE_LENGTH = 12


class AndroidAesGcmFieldCipher:
    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("AES-256-GCM requires a 32-byte key")
        self._key = key
        self._blind_key = hmac.new(key, b"aprendix:blind-index:v1", hashlib.sha256).digest()

    @staticmethod
    def _bridge():
        from jnius import autoclass
        return autoclass("io.aprendix.mobile.AprendixNativeBridge")

    def encrypt(self, plaintext: bytes, *, associated_data: bytes) -> bytes:
        nonce = secrets.token_bytes(NONCE_LENGTH)
        encrypted = bytes(self._bridge().aesGcmEncrypt(
            self._key, nonce, plaintext, associated_data
        ))
        return VERSION + nonce + encrypted

    def decrypt(self, envelope: bytes, *, associated_data: bytes) -> bytes:
        if len(envelope) < 29 or envelope[:1] != VERSION:
            raise ValueError("unsupported or truncated ciphertext")
        return bytes(self._bridge().aesGcmDecrypt(
            self._key, envelope[1:13], envelope[13:], associated_data
        ))

    def blind_index(self, value: bytes, *, namespace: bytes) -> bytes:
        if not namespace or len(namespace) > 120:
            raise ValueError("blind-index namespace must contain 1 to 120 bytes")
        return hmac.new(self._blind_key, namespace + b"\x00" + value, hashlib.sha256).digest()


def platform_field_cipher(key: bytes):
    if os.environ.get("ANDROID_ARGUMENT"):
        return AndroidAesGcmFieldCipher(key)
    from aprendix.infrastructure.security import AesGcmFieldCipher
    return AesGcmFieldCipher(key)
