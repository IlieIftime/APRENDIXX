"""Explicit offline packs plus the opt-in, separate HTTPS update broker."""

from __future__ import annotations

from pathlib import Path

from aprendix.infrastructure.update_broker import (
    ConnectivityState,
    ContentUpdateBroker,
    UpdatePolicy,
)


class ContentUpdateService:
    def __init__(self, manager, broker: ContentUpdateBroker | None = None) -> None:
        self._manager = manager
        self._broker = broker or ContentUpdateBroker(manager)

    def inspect(self, source: Path) -> dict[str, object]:
        pack = self._manager.verifier.verify(source)
        return {
            "pack_id": pack.pack_id, "version": pack.version,
            "file_count": pack.file_count, "total_bytes": pack.total_bytes,
            "license": pack.manifest["license"], "provenance": pack.manifest["provenance"],
        }

    def install(self, source: Path) -> dict[str, object]:
        pack = self._manager.install(
            source, validate_staging=self._manager.validate_declarative_staging,
        )
        return {"pack_id": pack.pack_id, "version": pack.version, "file_count": pack.file_count}

    def installed(self) -> tuple[dict[str, object], ...]:
        return self._manager.installed()

    def rollback(self, pack_id: str, version: str) -> None:
        self._manager.rollback(pack_id, version)

    @staticmethod
    def policy(registry_url: str, *, enabled: bool = True, channel: str = "stable",
               interval_days: int = 7, wifi_only: bool = False,
               external_power_only: bool = False) -> UpdatePolicy:
        from urllib.parse import urlsplit

        host = urlsplit(registry_url).hostname or ""
        return UpdatePolicy(
            enabled=enabled, registry_url=registry_url, allowed_hosts=(host,),
            channel=channel, interval_days=interval_days, wifi_only=wifi_only,
            external_power_only=external_power_only,
        )

    def check_remote(self, registry_url: str, *, force: bool = False,
                     channel: str = "stable", interval_days: int = 7,
                     wifi_only: bool = False, external_power_only: bool = False,
                     unmetered: bool | None = None,
                     external_power: bool | None = None) -> dict[str, object]:
        policy = self.policy(
            registry_url, channel=channel, interval_days=interval_days,
            wifi_only=wifi_only, external_power_only=external_power_only,
        )
        return self._broker.check(
            policy, force=force,
            connectivity=ConnectivityState(unmetered, external_power),
        )

    def install_remote(self, offer, registry_url: str, *, channel: str = "stable"):
        return self._broker.install(offer, self.policy(registry_url, channel=channel))

    def preview_remote(self, offer, registry_url: str, *, channel: str = "stable"):
        return self._broker.preview(offer, self.policy(registry_url, channel=channel))
