"""Signed, non-executable `.apxpack` validation and atomic activation."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

ALLOWED_SUFFIXES = {".md", ".txt", ".json", ".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_MIME = {"text/markdown", "text/plain", "application/json", "image/png", "image/jpeg", "image/webp"}
MAX_FILES = 1_000
MAX_TOTAL = 200 * 1024 * 1024


class ContentPackError(ValueError):
    pass


def canonical_json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass(frozen=True, slots=True)
class VerifiedPack:
    pack_id: str
    version: str
    manifest: dict[str, object]
    file_count: int
    total_bytes: int


class ApxPackVerifier:
    def __init__(self, public_keys: tuple[Ed25519PublicKey, ...]) -> None:
        if not public_keys: raise ValueError("É necessária pelo menos uma chave pública.")
        self._keys = public_keys

    def verify(self, path: Path) -> VerifiedPack:
        path = path.expanduser().resolve()
        if path.suffix.casefold() != ".apxpack" or not path.is_file() or path.stat().st_size > MAX_TOTAL:
            raise ContentPackError("Pack inexistente, formato ou tamanho inválido.")
        try:
            archive = zipfile.ZipFile(path)
        except zipfile.BadZipFile as exc:
            raise ContentPackError("Pack ZIP inválido.") from exc
        with archive:
            infos = archive.infolist()
            names = [item.filename for item in infos]
            if len(names) != len(set(names)) or len(names) > MAX_FILES + 2:
                raise ContentPackError("Pack contém nomes duplicados ou ficheiros em excesso.")
            if {"manifest.json", "signature.ed25519"} - set(names):
                raise ContentPackError("Manifesto ou assinatura em falta.")
            try:
                manifest_bytes = archive.read("manifest.json")
                manifest = json.loads(manifest_bytes)
                signature = archive.read("signature.ed25519")
            except (KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise ContentPackError("Manifesto inválido.") from exc
            if canonical_json(manifest) != manifest_bytes:
                raise ContentPackError("O manifesto não usa JSON canónico.")
            if not any(self._valid_signature(key, signature, manifest_bytes) for key in self._keys):
                raise ContentPackError("Assinatura Ed25519 inválida.")
            self._validate_manifest(manifest)
            expected = {item["path"]: item for item in manifest["files"]}
            actual = {name for name in names if name not in {"manifest.json", "signature.ed25519"}}
            if actual != set(expected):
                raise ContentPackError("Os ficheiros do pack não coincidem com o manifesto.")
            total = 0
            for info in infos:
                if info.filename in {"manifest.json", "signature.ed25519"}: continue
                self._safe_name(info)
                record = expected[info.filename]
                if info.file_size != record["size"] or info.file_size > MAX_TOTAL:
                    raise ContentPackError("Tamanho de ficheiro divergente.")
                if info.compress_size and info.file_size / info.compress_size > 100:
                    raise ContentPackError("Taxa de compressão suspeita (zip bomb).")
                total += info.file_size
                if total > MAX_TOTAL: raise ContentPackError("Conteúdo descomprimido excede 200 MB.")
                digest = hashlib.sha256()
                with archive.open(info) as stream:
                    for block in iter(lambda: stream.read(1024 * 1024), b""): digest.update(block)
                if digest.hexdigest() != record["sha256"]:
                    raise ContentPackError("Hash SHA-256 divergente.")
            return VerifiedPack(
                pack_id=manifest["pack_id"], version=manifest["version"], manifest=manifest,
                file_count=len(expected), total_bytes=total,
            )

    @staticmethod
    def _valid_signature(key, signature, payload):
        try: key.verify(signature, payload); return True
        except InvalidSignature: return False

    @staticmethod
    def _safe_name(info):
        name = info.filename
        pure = PurePosixPath(name)
        mode = info.external_attr >> 16
        if (not name or name.startswith(("/", "\\")) or "\\" in name or
                any(part in {"", ".", ".."} for part in pure.parts) or
                pure.suffix.casefold() not in ALLOWED_SUFFIXES or
                stat.S_ISLNK(mode) or stat.S_ISDIR(mode)):
            raise ContentPackError("Nome, extensão ou tipo de ficheiro proibido.")
        if not name.startswith(("content/", "media/", "delta/")):
            raise ContentPackError("Ficheiro fora das áreas declarativas permitidas.")

    @staticmethod
    def _validate_manifest(manifest):
        if not isinstance(manifest, dict) or set(manifest) != {
            "format", "pack_id", "version", "requires", "files", "license", "provenance"
        }:
            raise ContentPackError("Campos de manifesto inválidos.")
        if manifest["format"] != 1 or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{2,79}", str(manifest["pack_id"])):
            raise ContentPackError("Identidade/formato de pack inválido.")
        if not re.fullmatch(r"\d+\.\d+\.\d+", str(manifest["version"])):
            raise ContentPackError("Versão de pack inválida.")
        if not isinstance(manifest["requires"], list) or not isinstance(manifest["files"], list):
            raise ContentPackError("Dependências ou lista de ficheiros inválida.")
        for item in manifest["files"]:
            if not isinstance(item, dict) or set(item) != {"path", "sha256", "size", "mime"}:
                raise ContentPackError("Entrada de ficheiro inválida.")
            if item["mime"] not in ALLOWED_MIME or not re.fullmatch(r"[0-9a-f]{64}", str(item["sha256"])):
                raise ContentPackError("MIME ou hash não permitido.")
            if not isinstance(item["size"], int) or not 0 <= item["size"] <= MAX_TOTAL:
                raise ContentPackError("Tamanho declarado inválido.")
        if not str(manifest["license"]).strip() or not str(manifest["provenance"]).strip():
            raise ContentPackError("Licença e proveniência são obrigatórias.")


class ContentPackManager:
    def __init__(self, directory: Path, verifier: ApxPackVerifier, *, activator=None) -> None:
        self.directory = directory.expanduser().resolve(); self.verifier = verifier
        self._activator = activator
        self.directory.mkdir(parents=True, exist_ok=True)

    def install(self, pack_path: Path, *, validate_staging: Callable[[Path, VerifiedPack], None]) -> VerifiedPack:
        verified = self.verifier.verify(pack_path)
        destination = self.directory / verified.pack_id / verified.version
        active = self.directory / verified.pack_id / "active.json"
        if destination.exists():
            raise ContentPackError("Esta versão do pack já está instalada.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging = Path(tempfile.mkdtemp(prefix=".apxpack-", dir=destination.parent))
        destination_created = False
        try:
            with zipfile.ZipFile(pack_path) as archive:
                for record in verified.manifest["files"]:
                    target = staging.joinpath(*PurePosixPath(record["path"]).parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(record["path"]) as source, target.open("wb") as output:
                        shutil.copyfileobj(source, output, 1024 * 1024)
            (staging / "manifest.json").write_bytes(canonical_json(verified.manifest))
            validate_staging(staging, verified)
            os.replace(staging, destination)
            destination_created = True
            if self._activator is not None:
                self._activator(destination, verified)
            temporary = active.with_suffix(".tmp")
            temporary.write_bytes(canonical_json({"version": verified.version}))
            os.replace(temporary, active)
        except BaseException:
            if staging.exists(): shutil.rmtree(staging)
            if destination_created and destination.exists(): shutil.rmtree(destination)
            raise
        return verified

    def rollback(self, pack_id: str, version: str) -> None:
        self._validate_identity(pack_id, version)
        target = self.directory / pack_id / version
        if not target.resolve().is_relative_to(self.directory) or not target.is_dir():
            raise ContentPackError("Versão de rollback não instalada.")
        if self._activator is not None:
            self._activator(target, self._installed_pack(target))
        active = self.directory / pack_id / "active.json"
        temporary = active.with_suffix(".tmp")
        temporary.write_bytes(canonical_json({"version": version})); os.replace(temporary, active)

    @staticmethod
    def _installed_pack(directory: Path) -> VerifiedPack:
        try:
            manifest = json.loads((directory / "manifest.json").read_text("utf-8"))
            files = tuple(manifest["files"])
            return VerifiedPack(
                pack_id=str(manifest["pack_id"]), version=str(manifest["version"]),
                manifest=manifest, file_count=len(files),
                total_bytes=sum(int(item["size"]) for item in files),
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ContentPackError("Manifesto instalado inválido.") from exc

    def installed(self) -> tuple[dict[str, object], ...]:
        result: list[dict[str, object]] = []
        for pack_dir in sorted(self.directory.iterdir()):
            if not pack_dir.is_dir() or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{2,79}", pack_dir.name):
                continue
            active_version = ""
            try:
                active_version = str(json.loads((pack_dir / "active.json").read_text("utf-8"))["version"])
            except (OSError, KeyError, TypeError, json.JSONDecodeError):
                pass
            versions = tuple(
                child.name for child in sorted(pack_dir.iterdir())
                if child.is_dir() and re.fullmatch(r"\d+\.\d+\.\d+", child.name)
            )
            if not versions and not active_version:
                continue
            result.append({"pack_id": pack_dir.name, "active": active_version, "versions": versions})
        return tuple(result)

    @staticmethod
    def validate_declarative_staging(staging: Path, verified: VerifiedPack) -> None:
        """Parse each declarative file before it can become active."""
        for record in verified.manifest["files"]:
            path = staging.joinpath(*PurePosixPath(record["path"]).parts)
            suffix = path.suffix.casefold()
            if suffix == ".json":
                try:
                    json.loads(path.read_text("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ContentPackError(f"JSON inválido no pack: {record['path']}") from exc
            elif suffix in {".md", ".txt"}:
                try:
                    path.read_text("utf-8")
                except UnicodeDecodeError as exc:
                    raise ContentPackError(f"Texto não UTF-8 no pack: {record['path']}") from exc

    @staticmethod
    def _validate_identity(pack_id: str, version: str) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{2,79}", pack_id):
            raise ContentPackError("Identidade de pack inválida.")
        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ContentPackError("Versão de pack inválida.")


def build_pack(path: Path, manifest: dict[str, object], files: dict[str, bytes], key: Ed25519PrivateKey) -> Path:
    """Deterministic builder used by the trusted release pipeline and tests."""
    records = []
    mime_by_suffix = {".md": "text/markdown", ".txt": "text/plain", ".json": "application/json",
                      ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
    for name, payload in sorted(files.items()):
        records.append({"path": name, "sha256": hashlib.sha256(payload).hexdigest(),
                        "size": len(payload), "mime": mime_by_suffix[PurePosixPath(name).suffix.casefold()]})
    complete = {**manifest, "files": records}; payload = canonical_json(complete)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", payload); archive.writestr("signature.ed25519", key.sign(payload))
        for name, content in sorted(files.items()): archive.writestr(name, content)
    return path
