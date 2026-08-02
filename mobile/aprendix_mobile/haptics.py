"""Small platform haptics port with a silent accessibility-safe fallback."""

from __future__ import annotations

import os
import sys


class Haptics:
    def emit(self, pattern: str) -> None:
        if pattern not in {"accept", "success", "error"}:
            raise ValueError("unknown haptic pattern")
        try:
            if os.environ.get("ANDROID_ARGUMENT"):
                from jnius import autoclass
                autoclass("io.aprendix.mobile.AprendixNativeBridge").haptic(pattern)
            elif sys.platform == "ios":
                from rubicon.objc import ObjCClass
                ObjCClass("AprendixKeychainBridge").haptic_(pattern)
        except (ImportError, RuntimeError):
            return

