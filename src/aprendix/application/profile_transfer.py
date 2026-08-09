"""Password-protected, versioned profile transfer without a cloud account."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

LEGACY_MAGIC = b"APXPROFILE\x01"
MAGIC = b"APXPROFILE\x02"
MAX_RECORDS_PER_SECTION = 100_000
MAX_TEXT_LENGTH = 100_000
PROFILE_SECTIONS = ("reviews", "attempts", "completed_units", "projects")


class ProfileTransferError(ValueError):
    pass


def validate_snapshot(snapshot: object) -> dict[str, object]:
    """Return a bounded, JSON-safe profile snapshot.

    Authentication protects a profile in transit; this validation protects the
    importer from a correctly encrypted but malformed or excessively large
    document created by another client.
    """
    if not isinstance(snapshot, dict):
        raise ProfileTransferError("Conteudo de perfil invalido.")
    platform = snapshot.get("platform", "unknown")
    if not isinstance(platform, str) or not 1 <= len(platform) <= 32:
        raise ProfileTransferError("Plataforma de perfil invalida.")
    normalized: dict[str, object] = {"platform": platform}
    for section in PROFILE_SECTIONS:
        records = snapshot.get(section, [])
        if not isinstance(records, list) or len(records) > MAX_RECORDS_PER_SECTION:
            raise ProfileTransferError(f"Seccao de perfil invalida: {section}.")
        clean: list[dict[str, object]] = []
        identities: set[str] = set()
        for record in records:
            if not isinstance(record, dict) or "id" not in record:
                raise ProfileTransferError(f"Registo de perfil invalido: {section}.")
            identity = str(record["id"])
            if not identity or len(identity) > 200 or identity in identities:
                raise ProfileTransferError(f"Identidade duplicada ou invalida: {section}.")
            identities.add(identity)
            for key, value in record.items():
                if not isinstance(key, str) or len(key) > 80:
                    raise ProfileTransferError("Campo de perfil invalido.")
                if isinstance(value, str) and len(value) > MAX_TEXT_LENGTH:
                    raise ProfileTransferError("Texto de perfil demasiado extenso.")
                if isinstance(value, (dict, list)):
                    raise ProfileTransferError("Estruturas aninhadas nao sao permitidas no perfil.")
                if value is not None and not isinstance(value, (str, int, float, bool)):
                    raise ProfileTransferError("Valor de perfil invalido.")
            clean.append(dict(record))
        normalized[section] = clean
    return normalized


def _key(passphrase: str, salt: bytes, *, legacy: bool = False) -> bytes:
    if len(passphrase) < 10:
        raise ProfileTransferError("A frase-passe precisa de pelo menos 10 caracteres.")
    if legacy:
        if os.environ.get("ANDROID_ARGUMENT"):
            raise ProfileTransferError(
                "Perfil legado: abre-o no desktop e volta a exportá-lo para o formato atual."
            )
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        return Scrypt(salt=salt, length=32, n=2**15, r=8, p=1).derive(passphrase.encode("utf-8"))
    return hashlib.pbkdf2_hmac("sha256", passphrase.encode("utf-8"), salt, 600_000, dklen=32)


def _encrypt(key: bytes, nonce: bytes, plaintext: bytes, aad: bytes) -> bytes:
    if os.environ.get("ANDROID_ARGUMENT"):
        from jnius import autoclass
        bridge = autoclass("io.aprendix.mobile.AprendixNativeBridge")
        return bytes(bridge.aesGcmEncrypt(key, nonce, plaintext, aad))
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key).encrypt(nonce, plaintext, aad)


def _decrypt(key: bytes, nonce: bytes, ciphertext: bytes, aad: bytes) -> bytes:
    if os.environ.get("ANDROID_ARGUMENT"):
        from jnius import autoclass
        bridge = autoclass("io.aprendix.mobile.AprendixNativeBridge")
        return bytes(bridge.aesGcmDecrypt(key, nonce, ciphertext, aad))
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    return AESGCM(key).decrypt(nonce, ciphertext, aad)


def write_profile(path: Path, passphrase: str, snapshot: dict[str, object]) -> Path:
    path = path.expanduser().resolve()
    if path.suffix.casefold() != ".apxprofile":
        raise ProfileTransferError("O ficheiro deve terminar em .apxprofile")
    envelope = {
        "format": 1, "exported_at": datetime.now(timezone.utc).isoformat(),
        "snapshot": validate_snapshot(snapshot),
    }
    payload = json.dumps(envelope, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    salt, nonce = secrets.token_bytes(16), secrets.token_bytes(12)
    encrypted = _encrypt(_key(passphrase, salt), nonce, payload, MAGIC)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_bytes(MAGIC + salt + nonce + encrypted)
    temporary.replace(path)
    return path


def read_profile(path: Path, passphrase: str, *, max_bytes: int = 64 * 1024 * 1024) -> dict[str, object]:
    path = path.expanduser().resolve()
    size = path.stat().st_size
    if size < len(MAGIC) + 16 + 12 + 16 or size > max_bytes:
        raise ProfileTransferError("Tamanho de perfil inválido.")
    data = path.read_bytes()
    magic = LEGACY_MAGIC if data.startswith(LEGACY_MAGIC) else MAGIC if data.startswith(MAGIC) else None
    if magic is None:
        raise ProfileTransferError("Formato de perfil desconhecido.")
    cursor = len(magic); salt = data[cursor:cursor+16]; nonce = data[cursor+16:cursor+28]
    try:
        plain = _decrypt(
            _key(passphrase, salt, legacy=magic == LEGACY_MAGIC),
            nonce, data[cursor+28:], magic,
        )
        envelope = json.loads(plain)
    except (ProfileTransferError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProfileTransferError("Frase-passe incorreta ou ficheiro alterado.") from exc
    except Exception as exc:
        raise ProfileTransferError("Frase-passe incorreta ou ficheiro alterado.") from exc
    if not isinstance(envelope, dict) or envelope.get("format") != 1 or not isinstance(envelope.get("snapshot"), dict):
        raise ProfileTransferError("Conteúdo de perfil inválido.")
    return validate_snapshot(envelope["snapshot"])


def merge_by_identity(
    local: list[dict[str, object]], incoming: list[dict[str, object]], *,
    identity: str = "id", timestamp: str = "updated_at",
) -> tuple[list[dict[str, object]], tuple[dict[str, object], ...]]:
    """Last-write-wins with deterministic tie-breaking and explicit conflict preview."""
    if any(not isinstance(item, dict) or identity not in item for item in (*local, *incoming)):
        raise ProfileTransferError("Registo sem identidade no perfil.")
    merged = {str(item[identity]): dict(item) for item in local}
    conflicts = []
    for item in incoming:
        key = str(item[identity]); current = merged.get(key)
        if current is None:
            merged[key] = dict(item); continue
        if current == item:
            continue
        current_time, incoming_time = str(current.get(timestamp, "")), str(item.get(timestamp, ""))
        winner = item if (incoming_time, json.dumps(item, sort_keys=True)) > (
            current_time, json.dumps(current, sort_keys=True)
        ) else current
        conflicts.append({"id": key, "local": current, "incoming": item, "winner": winner})
        merged[key] = dict(winner)
    return [merged[key] for key in sorted(merged)], tuple(conflicts)
