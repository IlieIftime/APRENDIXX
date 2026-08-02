"""Platform-owned paths; no project or desktop paths are used at runtime."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class PlatformPaths:
    data: Path
    cache: Path
    resources: Path

    @classmethod
    def resolve(
        cls, *, user_data_dir: str | Path | None = None,
        cache_dir: str | Path | None = None,
        resources_dir: str | Path | None = None,
    ) -> "PlatformPaths":
        resources = Path(resources_dir or Path(__file__).resolve().parents[1] / "assets")
        if user_data_dir is not None:
            data = Path(user_data_dir)
        elif os.environ.get("ANDROID_ARGUMENT"):
            data = cls._android_directory("getFilesDir")
        elif sys.platform == "ios":
            data = Path.home() / "Library" / "Application Support" / "Aprendix"
        else:
            data = Path(os.environ.get("APRENDIX_MOBILE_DATA", Path.home() / ".aprendix-mobile"))
        if cache_dir is not None:
            cache = Path(cache_dir)
        elif os.environ.get("ANDROID_ARGUMENT"):
            cache = cls._android_directory("getCacheDir")
        elif sys.platform == "ios":
            cache = Path.home() / "Library" / "Caches" / "Aprendix"
        else:
            cache = data / "cache"
        result = cls(data.resolve(), cache.resolve(), resources.resolve())
        result.ensure()
        return result

    @staticmethod
    def _android_directory(method: str) -> Path:
        try:
            from jnius import autoclass
            activity = autoclass("org.kivy.android.PythonActivity").mActivity
            return Path(str(getattr(activity, method)().getAbsolutePath()))
        except (ImportError, AttributeError) as exc:
            raise RuntimeError("Android application paths are unavailable") from exc

    def ensure(self) -> None:
        for directory in (self.data, self.cache):
            directory.mkdir(parents=True, exist_ok=True)
        (self.data / "state").mkdir(exist_ok=True)
        (self.data / "keys").mkdir(exist_ok=True)

    @property
    def user_database(self) -> Path:
        return self.data / "user.db"

    @property
    def content_database(self) -> Path:
        return self.data / "knowledge-lite.db"

    @property
    def durable_queue(self) -> Path:
        return self.data / "state" / "sync-queue.bin"

