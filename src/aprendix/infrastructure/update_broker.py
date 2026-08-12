"""Opt-in HTTPS discovery and atomic installation of signed content packs."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import ssl
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Callable, Protocol

from aprendix.infrastructure.content_pack import ContentPackError, MAX_TOTAL, canonical_json


MAX_REGISTRY_BYTES = 1024 * 1024
_PACK_ID = re.compile(r"[a-z0-9][a-z0-9.-]{2,79}")
_VERSION = re.compile(r"\d+\.\d+\.\d+")
_SHA256 = re.compile(r"[0-9a-f]{64}")


class UpdateBrokerError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ConnectivityState:
    unmetered: bool | None = None
    external_power: bool | None = None


@dataclass(frozen=True, slots=True)
class UpdatePolicy:
    enabled: bool
    registry_url: str
    allowed_hosts: tuple[str, ...]
    channel: str = "stable"
    interval_days: int = 7
    wifi_only: bool = False
    external_power_only: bool = False

    def __post_init__(self) -> None:
        if self.channel not in {"stable", "preview"}:
            raise UpdateBrokerError("Canal de atualização inválido.")
        if not 1 <= self.interval_days <= 30:
            raise UpdateBrokerError("O intervalo deve ficar entre 1 e 30 dias.")
        parsed = urllib.parse.urlsplit(self.registry_url)
        hosts = tuple(host.casefold().strip(".") for host in self.allowed_hosts if host.strip("."))
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            raise UpdateBrokerError("O registo de atualizações tem de usar HTTPS sem credenciais no URL.")
        if parsed.port not in {None, 443} or parsed.hostname.casefold() not in hosts:
            raise UpdateBrokerError("O host do registo não pertence à allowlist.")


@dataclass(frozen=True, slots=True)
class RemotePackOffer:
    pack_id: str
    version: str
    title: str
    summary: str
    url: str
    sha256: str
    size: int
    published_at: str
    sources: tuple[str, ...]
    affected_tracks: tuple[str, ...]
    channel: str = "stable"


@dataclass(frozen=True, slots=True)
class FetchResponse:
    status: int
    body: bytes
    etag: str = ""
    last_modified: str = ""


class UpdateClient(Protocol):
    def fetch(self, url: str, *, max_bytes: int, etag: str = "",
              last_modified: str = "") -> FetchResponse: ...

    def download(self, url: str, destination: Path, *, max_bytes: int) -> tuple[int, str]: ...


class _AllowlistedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: frozenset[str]) -> None:
        super().__init__()
        self._allowed_hosts = allowed_hosts

    def redirect_request(self, request, file_pointer, code, message, headers, new_url):
        _validate_https_url(new_url, self._allowed_hosts)
        return super().redirect_request(request, file_pointer, code, message, headers, new_url)


def _validate_https_url(url: str, allowed_hosts: frozenset[str]) -> None:
    parsed = urllib.parse.urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.port not in {None, 443}
            or parsed.hostname.casefold() not in allowed_hosts):
        raise UpdateBrokerError("URL fora da allowlist HTTPS do registo.")


class HttpsUpdateClient:
    """Small bounded client; it never sends cookies or authentication data."""

    def __init__(self, allowed_hosts: tuple[str, ...], *, timeout_seconds: float = 15.0) -> None:
        self._hosts = frozenset(host.casefold().strip(".") for host in allowed_hosts)
        if not self._hosts:
            raise UpdateBrokerError("A allowlist de atualização está vazia.")
        self._timeout = max(2.0, min(float(timeout_seconds), 60.0))
        context = ssl.create_default_context()
        self._opener = urllib.request.build_opener(
            urllib.request.HTTPSHandler(context=context),
            _AllowlistedRedirectHandler(self._hosts),
        )

    @staticmethod
    def _request(url: str, headers: dict[str, str] | None = None):
        return urllib.request.Request(
            url,
            headers={"Accept": "application/json, application/octet-stream", "User-Agent": "Aprendix-UpdateBroker/1", **(headers or {})},
            method="GET",
        )

    def fetch(self, url: str, *, max_bytes: int, etag: str = "",
              last_modified: str = "") -> FetchResponse:
        _validate_https_url(url, self._hosts)
        headers = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        try:
            response = self._opener.open(self._request(url, headers), timeout=self._timeout)
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return FetchResponse(304, b"", etag, last_modified)
            raise UpdateBrokerError(f"O registo respondeu HTTP {exc.code}.") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise UpdateBrokerError("Não foi possível contactar o registo de atualizações.") from exc
        with response:
            length = response.headers.get("Content-Length")
            if length and int(length) > max_bytes:
                raise UpdateBrokerError("A resposta excede o limite permitido.")
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise UpdateBrokerError("A resposta excede o limite permitido.")
            return FetchResponse(
                int(response.status), body,
                response.headers.get("ETag", "")[:500],
                response.headers.get("Last-Modified", "")[:500],
            )

    def download(self, url: str, destination: Path, *, max_bytes: int) -> tuple[int, str]:
        _validate_https_url(url, self._hosts)
        digest, total = hashlib.sha256(), 0
        try:
            response = self._opener.open(self._request(url), timeout=self._timeout)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            raise UpdateBrokerError("Não foi possível descarregar o pack.") from exc
        with response, destination.open("xb") as output:
            length = response.headers.get("Content-Length")
            if length and int(length) > max_bytes:
                raise UpdateBrokerError("O pack excede o limite permitido.")
            while True:
                block = response.read(min(1024 * 1024, max_bytes - total + 1))
                if not block:
                    break
                total += len(block)
                if total > max_bytes:
                    raise UpdateBrokerError("O pack excede o limite permitido.")
                digest.update(block)
                output.write(block)
        return total, digest.hexdigest()


def _parse_timestamp(value: object) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise UpdateBrokerError("Data de publicação inválida no registo.") from exc
    if parsed.tzinfo is None:
        raise UpdateBrokerError("A data de publicação tem de indicar timezone.")
    return parsed.astimezone(UTC).isoformat()


def _parse_offer(value: object, *, allowed_hosts: frozenset[str]) -> RemotePackOffer:
    required = {
        "pack_id", "version", "title", "summary", "url", "sha256", "size",
        "published_at", "sources", "affected_tracks", "channel",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise UpdateBrokerError("Entrada de pack inválida no registo.")
    pack_id, version = str(value["pack_id"]), str(value["version"])
    title, summary = str(value["title"]).strip(), str(value["summary"]).strip()
    digest, size = str(value["sha256"]), value["size"]
    channel = str(value["channel"])
    if (not _PACK_ID.fullmatch(pack_id) or not _VERSION.fullmatch(version)
            or not _SHA256.fullmatch(digest) or not isinstance(size, int)
            or not 1 <= size <= MAX_TOTAL or not 1 <= len(title) <= 200
            or not 1 <= len(summary) <= 1_000 or channel not in {"stable", "preview"}):
        raise UpdateBrokerError("Metadados de pack inválidos no registo.")
    _validate_https_url(str(value["url"]), allowed_hosts)
    if not isinstance(value["sources"], list) or not isinstance(value["affected_tracks"], list):
        raise UpdateBrokerError("Fontes e percursos do pack têm de ser listas.")
    sources = tuple(str(item).strip() for item in value["sources"])
    tracks = tuple(str(item).strip() for item in value["affected_tracks"])
    if (not sources or len(sources) > 50 or len(tracks) > 50
            or any(not item or len(item) > 200 for item in (*sources, *tracks))):
        raise UpdateBrokerError("Fontes ou percursos inválidos no registo.")
    return RemotePackOffer(
        pack_id, version, title, summary, str(value["url"]), digest, size,
        _parse_timestamp(value["published_at"]), sources, tracks, channel,
    )


def parse_registry(payload: bytes, *, allowed_hosts: tuple[str, ...],
                   channel: str) -> tuple[RemotePackOffer, ...]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateBrokerError("O registo não contém JSON UTF-8 válido.") from exc
    if not isinstance(value, dict) or set(value) != {"format", "generated_at", "packs"}:
        raise UpdateBrokerError("Formato do registo de atualizações inválido.")
    if value["format"] != 1 or not isinstance(value["packs"], list) or len(value["packs"]) > 1_000:
        raise UpdateBrokerError("Versão ou tamanho do registo inválido.")
    _parse_timestamp(value["generated_at"])
    hosts = frozenset(host.casefold().strip(".") for host in allowed_hosts)
    offers = tuple(_parse_offer(item, allowed_hosts=hosts) for item in value["packs"])
    identities = {(item.pack_id, item.version) for item in offers}
    if len(identities) != len(offers):
        raise UpdateBrokerError("O registo contém packs duplicados.")
    return tuple(item for item in offers if item.channel == channel)


class ContentUpdateBroker:
    def __init__(self, manager, *, client_factory: Callable[[tuple[str, ...]], UpdateClient] = HttpsUpdateClient) -> None:
        self._manager = manager
        self._client_factory = client_factory
        self._state_dir = manager.directory / ".broker"
        self._quarantine = self._state_dir / "quarantine"
        self._state_path = self._state_dir / "state.json"
        self._state_dir.mkdir(parents=True, exist_ok=True)

    def _read_state(self) -> dict[str, object]:
        try:
            value = json.loads(self._state_path.read_text("utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return {}

    def _write_state(self, state: dict[str, object]) -> None:
        temporary = self._state_path.with_suffix(".tmp")
        temporary.write_bytes(canonical_json(state))
        os.replace(temporary, self._state_path)

    @staticmethod
    def _connectivity_block(policy: UpdatePolicy, connectivity: ConnectivityState) -> str:
        if policy.wifi_only and connectivity.unmetered is not True:
            return "A atualização aguarda uma ligação não medida/Wi-Fi confirmada."
        if policy.external_power_only and connectivity.external_power is not True:
            return "A atualização aguarda alimentação externa confirmada."
        return ""

    def check(self, policy: UpdatePolicy, *, connectivity: ConnectivityState = ConnectivityState(),
              force: bool = False) -> dict[str, object]:
        if not policy.enabled:
            return {"status": "disabled", "offers": (), "checked_at": ""}
        blocked = self._connectivity_block(policy, connectivity)
        if blocked:
            return {"status": "deferred", "reason": blocked, "offers": (), "checked_at": ""}
        state = self._read_state()
        now = datetime.now(UTC)
        try:
            last = datetime.fromisoformat(str(state.get("checked_at", "")))
        except ValueError:
            last = None
        if (not force and last is not None and now - last < timedelta(days=policy.interval_days)
                and state.get("registry_url") == policy.registry_url
                and state.get("channel") == policy.channel):
            offers = self._offers_from_state(state, policy)
            installed = {row["pack_id"]: row["active"] for row in self._manager.installed()}
            available = tuple(item for item in offers if installed.get(item.pack_id) != item.version)
            return {"status": "cached", "offers": available, "checked_at": last.isoformat()}
        client = self._client_factory(policy.allowed_hosts)
        response = client.fetch(
            policy.registry_url, max_bytes=MAX_REGISTRY_BYTES,
            etag=str(state.get("etag", "")), last_modified=str(state.get("last_modified", "")),
        )
        if response.status == 304:
            offers = self._offers_from_state(state, policy)
        elif response.status == 200:
            offers = parse_registry(response.body, allowed_hosts=policy.allowed_hosts, channel=policy.channel)
            state["offers"] = [asdict(item) for item in offers]
        else:
            raise UpdateBrokerError(f"Estado HTTP inesperado: {response.status}.")
        installed = {row["pack_id"]: row["active"] for row in self._manager.installed()}
        available = tuple(item for item in offers if installed.get(item.pack_id) != item.version)
        state.update({
            "format": 1, "registry_url": policy.registry_url, "channel": policy.channel,
            "checked_at": now.isoformat(), "etag": response.etag,
            "last_modified": response.last_modified,
        })
        self._write_state(state)
        return {"status": "checked" if response.status == 200 else "not-modified",
                "offers": available, "checked_at": now.isoformat()}

    def _offers_from_state(self, state: dict[str, object], policy: UpdatePolicy) -> tuple[RemotePackOffer, ...]:
        hosts = frozenset(host.casefold().strip(".") for host in policy.allowed_hosts)
        values = state.get("offers", [])
        if not isinstance(values, list):
            return ()
        return tuple(_parse_offer(value, allowed_hosts=hosts) for value in values)

    def install(self, offer: RemotePackOffer, policy: UpdatePolicy) -> dict[str, object]:
        self.preview(offer, policy)
        client = self._client_factory(policy.allowed_hosts)
        temporary_dir = Path(tempfile.mkdtemp(prefix=".download-", dir=self._state_dir))
        downloaded = temporary_dir / f"{offer.pack_id}-{offer.version}.apxpack"
        try:
            size, digest = client.download(offer.url, downloaded, max_bytes=min(MAX_TOTAL, offer.size))
            if size != offer.size or digest != offer.sha256:
                raise UpdateBrokerError("O download não coincide com tamanho/SHA-256 publicados.")
            verified = self._manager.install(
                downloaded, validate_staging=self._manager.validate_declarative_staging,
            )
            return {"pack_id": verified.pack_id, "version": verified.version,
                    "file_count": verified.file_count, "total_bytes": verified.total_bytes}
        except (ContentPackError, UpdateBrokerError):
            if downloaded.is_file():
                self._quarantine.mkdir(parents=True, exist_ok=True)
                quarantine_path = self._quarantine / f"{offer.sha256}.apxpack"
                if not quarantine_path.exists():
                    os.replace(downloaded, quarantine_path)
                self._trim_quarantine()
            raise
        finally:
            shutil.rmtree(temporary_dir, ignore_errors=True)

    def preview(self, offer: RemotePackOffer, policy: UpdatePolicy) -> dict[str, object]:
        """Validate and describe an update without downloading or changing state."""
        hosts = frozenset(host.casefold().strip(".") for host in policy.allowed_hosts)
        _validate_https_url(offer.url, hosts)
        if offer.channel != policy.channel:
            raise UpdateBrokerError("O pack não pertence ao canal selecionado.")
        installed = {row["pack_id"]: row["active"] for row in self._manager.installed()}
        previous = installed.get(offer.pack_id)
        return {
            "pack_id": offer.pack_id, "version": offer.version,
            "title": offer.title, "summary": offer.summary,
            "published_at": offer.published_at, "total_bytes": offer.size,
            "sources": offer.sources, "affected_tracks": offer.affected_tracks,
            "replaces": previous or "", "rollback_available": bool(previous),
            "requires_confirmation": True, "uploads_user_data": False,
            "channel": offer.channel,
        }

    def _trim_quarantine(self) -> None:
        files = sorted(
            (path for path in self._quarantine.glob("*.apxpack") if path.is_file()),
            key=lambda path: path.stat().st_mtime, reverse=True,
        )
        for path in files[3:]:
            path.unlink(missing_ok=True)
