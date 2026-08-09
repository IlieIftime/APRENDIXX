"""Android Storage Access Framework bridge for portable profile files."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4


class DocumentPortalError(RuntimeError):
    pass


class AndroidDocumentPortal:
    CREATE_REQUEST = 7711
    OPEN_REQUEST = 7712
    IMAGE_REQUEST = 7713
    CAMERA_REQUEST = 7714

    def __init__(self, cache_directory: Path) -> None:
        self.cache_directory = cache_directory
        self.cache_directory.mkdir(parents=True, exist_ok=True)
        self._pending: dict[int, tuple[Path | None, object]] = {}
        self._bound = False

    @property
    def available(self) -> bool:
        return bool(os.environ.get("ANDROID_ARGUMENT"))

    def export_file(self, source: Path, callback) -> None:
        if not self.available:
            raise DocumentPortalError("O seletor nativo só está disponível no Android.")
        Intent, activity, current = self._android()
        self._bind(activity)
        intent = Intent(Intent.ACTION_CREATE_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType("application/octet-stream")
        intent.putExtra(Intent.EXTRA_TITLE, source.name)
        self._pending[self.CREATE_REQUEST] = (source, callback)
        current.startActivityForResult(intent, self.CREATE_REQUEST)

    def import_file(self, callback) -> None:
        if not self.available:
            raise DocumentPortalError("O seletor nativo só está disponível no Android.")
        Intent, activity, current = self._android()
        self._bind(activity)
        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType("application/octet-stream")
        self._pending[self.OPEN_REQUEST] = (None, callback)
        current.startActivityForResult(intent, self.OPEN_REQUEST)

    def import_image(self, callback) -> None:
        if not self.available:
            raise DocumentPortalError("O seletor nativo só está disponível no Android.")
        Intent, activity, current = self._android()
        self._bind(activity)
        intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
        intent.addCategory(Intent.CATEGORY_OPENABLE)
        intent.setType("image/*")
        self._pending[self.IMAGE_REQUEST] = (None, callback)
        current.startActivityForResult(intent, self.IMAGE_REQUEST)

    def capture_image(self, callback) -> None:
        if not self.available:
            raise DocumentPortalError("A câmara nativa só está disponível no Android.")
        Intent, activity, current = self._android()
        from jnius import autoclass
        self._bind(activity)
        intent = Intent(autoclass("android.provider.MediaStore").ACTION_IMAGE_CAPTURE)
        self._pending[self.CAMERA_REQUEST] = (None, callback)
        current.startActivityForResult(intent, self.CAMERA_REQUEST)

    @staticmethod
    def _android():
        from android import activity
        from jnius import autoclass
        return autoclass("android.content.Intent"), activity, autoclass(
            "org.kivy.android.PythonActivity"
        ).mActivity

    def _bind(self, activity) -> None:
        if not self._bound:
            activity.bind(on_activity_result=self._on_result)
            self._bound = True

    def _on_result(self, request_code, result_code, intent) -> None:
        pending = self._pending.pop(int(request_code), None)
        if pending is None:
            return
        source, callback = pending
        try:
            if int(result_code) != -1 or intent is None:
                callback(None, "Operação cancelada.")
                return
            uri = intent.getData()
            _Intent, _activity, current = self._android()
            if int(request_code) == self.CAMERA_REQUEST:
                extras = intent.getExtras()
                bitmap = extras.get("data") if extras is not None else None
                if bitmap is None:
                    callback(None, "A câmara não devolveu uma imagem.")
                    return
                from jnius import autoclass
                destination = self.cache_directory / f"camera-{uuid4()}.png"
                output_stream = autoclass("java.io.FileOutputStream")(str(destination))
                try:
                    bitmap.compress(
                        autoclass("android.graphics.Bitmap$CompressFormat").PNG,
                        100, output_stream,
                    )
                    output_stream.flush()
                finally:
                    output_stream.close()
                callback(destination, None)
                return
            resolver = current.getContentResolver()
            if int(request_code) == self.CREATE_REQUEST:
                descriptor = resolver.openFileDescriptor(uri, "w")
                try:
                    with source.open("rb") as input_stream, os.fdopen(
                        os.dup(descriptor.getFd()), "wb"
                    ) as output_stream:
                        shutil.copyfileobj(input_stream, output_stream, 1024 * 1024)
                        output_stream.flush()
                finally:
                    descriptor.close()
                callback(source, None)
            else:
                suffix = ".image" if int(request_code) == self.IMAGE_REQUEST else ".apxprofile"
                destination = self.cache_directory / f"import-{uuid4()}{suffix}"
                descriptor = resolver.openFileDescriptor(uri, "r")
                try:
                    with os.fdopen(os.dup(descriptor.getFd()), "rb") as input_stream, destination.open("wb") as output_stream:
                        shutil.copyfileobj(input_stream, output_stream, 1024 * 1024)
                finally:
                    descriptor.close()
                callback(destination, None)
        except Exception as exc:
            callback(None, str(exc))


def document_portal(cache_directory: Path):
    if os.environ.get("ANDROID_ARGUMENT"):
        return AndroidDocumentPortal(cache_directory)
    # iOS uses the native Toga shell; the Kivy package is Android-only in the
    # current release. Keep host dry-runs explicit rather than writing silently.
    if sys.platform == "ios":
        raise DocumentPortalError("Usa o seletor de documentos do shell iOS.")
    return AndroidDocumentPortal(cache_directory)
