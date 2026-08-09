"""Use case for explicit, password-protected profile portability."""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from aprendix.application.profile_transfer import read_profile, write_profile


class ProfileTransferService:
    def __init__(self, user_id: UUID, repository) -> None:
        self._user_id, self._repository = user_id, repository

    def export(self, destination: Path, passphrase: str) -> Path:
        return write_profile(destination, passphrase, self._repository.export_snapshot(self._user_id))

    def preview(self, source: Path, passphrase: str) -> dict[str, int]:
        return self._repository.preview_snapshot(self._user_id, read_profile(source, passphrase))

    def import_file(self, source: Path, passphrase: str) -> dict[str, int]:
        return self._repository.import_snapshot(self._user_id, read_profile(source, passphrase))
