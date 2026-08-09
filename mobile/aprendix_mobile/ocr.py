"""Native offline OCR bridges for Android ML Kit and iOS Vision."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from aprendix_mobile.contracts import OcrDraftDTO, OcrRegionDTO


class MobileOcr:
    def extract(self, path: Path) -> OcrDraftDTO:
        path = path.expanduser().resolve()
        if not path.is_file() or path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("Imagem inexistente ou superior a 20 MB.")
        text = ""
        if os.environ.get("ANDROID_ARGUMENT"):
            from jnius import autoclass
            bridge = autoclass("io.aprendix.mobile.AprendixNativeBridge")
            text = str(bridge.ocrFile(str(path)))
        elif sys.platform == "ios":
            from rubicon.objc import ObjCClass
            value = ObjCClass("AprendixKeychainBridge").recognizeTextAtPath_(str(path))
            text = str(value or "")
        else:
            from aprendix.infrastructure.image_ocr import LocalImageOcr
            return LocalImageOcr().extract(path)
        regions = tuple(
            OcrRegionDTO(text=line, confidence=.9, ambiguous=bool(set(line) & set("OlI1:;")))
            for line in text.splitlines() if line.strip()
        )
        return OcrDraftDTO(
            text=text, confidence=(.9 if regions else 0), regions=regions,
            warnings=(("Confirma indentações e caracteres ambíguos antes da análise.",)
                      if regions else ("Não foi detetado texto legível.",)),
            requires_confirmation=True,
        )
