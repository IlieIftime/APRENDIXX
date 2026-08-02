"""Per-installation data keys backed by native secure stores."""

from __future__ import annotations

import os
import secrets
import sys
from pathlib import Path
from typing import Protocol


class DeviceKeyProvider(Protocol):
    def get_or_create_key(self) -> bytes: ...


class MissingDeviceKeyError(RuntimeError):
    """The encrypted user database exists but its device key is unavailable."""


class AndroidKeystoreProvider:
    """Use a non-exportable Android Keystore KEK to wrap a random DEK."""

    def __init__(self, wrapped_key_path: Path, *, database_path: Path) -> None:
        self._wrapped = wrapped_key_path
        self._database = database_path

    def get_or_create_key(self) -> bytes:
        try:
            from jnius import autoclass
            bridge = autoclass("io.aprendix.mobile.AprendixKeyStoreBridge")
        except ImportError as exc:
            raise RuntimeError("pyjnius is required for Android Keystore") from exc
        if self._database.exists() and not self._wrapped.exists():
            raise MissingDeviceKeyError("user database exists but wrapped device key is missing")
        self._wrapped.parent.mkdir(parents=True, exist_ok=True)
        value = bytes(bridge.getOrCreate(str(self._wrapped)))
        if len(value) != 32:
            raise MissingDeviceKeyError("Android Keystore returned an invalid data key")
        return value


class IOSKeychainProvider:
    """Store a ThisDeviceOnly DEK through the bundled Objective-C bridge."""

    def __init__(self, *, database_path: Path, service: str = "io.aprendix.mobile") -> None:
        self._database = database_path
        self._service = service

    def get_or_create_key(self) -> bytes:
        try:
            from rubicon.objc import ObjCClass
            bridge = ObjCClass("AprendixKeychainBridge")
        except ImportError as exc:
            raise RuntimeError("Rubicon Objective-C is required for iOS Keychain") from exc
        existing = bridge.keyForService_account_(self._service, "fields-v1")
        if existing is None and self._database.exists():
            raise MissingDeviceKeyError("user database exists but Keychain key is missing")
        if existing is None:
            key = secrets.token_bytes(32)
            if not bridge.storeKey_service_account_(key, self._service, "fields-v1"):
                raise MissingDeviceKeyError("iOS Keychain refused the device key")
            return key
        value = bytes(existing)
        if len(value) != 32:
            raise MissingDeviceKeyError("iOS Keychain returned an invalid data key")
        return value


class HostDevelopmentKeyProvider:
    """Explicit test/development fallback; mobile entrypoints never select it."""

    def __init__(self, path: Path, *, database_path: Path, allow: bool = False) -> None:
        if not allow:
            raise RuntimeError("host key files require an explicit development opt-in")
        self._path, self._database = path, database_path

    def get_or_create_key(self) -> bytes:
        if self._path.exists():
            value = self._path.read_bytes()
            if len(value) != 32: raise MissingDeviceKeyError("invalid development key")
            return value
        if self._database.exists():
            raise MissingDeviceKeyError("database exists but development key is missing")
        self._path.parent.mkdir(parents=True, exist_ok=True)
        value = secrets.token_bytes(32)
        descriptor = os.open(self._path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        return value


def device_key_provider(data: Path, database: Path) -> DeviceKeyProvider:
    if os.environ.get("ANDROID_ARGUMENT"):
        return AndroidKeystoreProvider(data / "keys" / "fields.wrapped", database_path=database)
    if sys.platform == "ios":
        return IOSKeychainProvider(database_path=database)
    raise RuntimeError("production device keys are only available on Android and iOS")
