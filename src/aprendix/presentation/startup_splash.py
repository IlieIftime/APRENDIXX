"""Tiny dependency-free Windows startup notice for the packaged desktop app."""

from __future__ import annotations

import os
import threading


_TITLE = "Aprendix · a iniciar"
_thread: threading.Thread | None = None


def start_startup_splash() -> None:
    """Show a responsive native notice while the local runtime is prepared."""

    global _thread
    if os.name != "nt" or (_thread is not None and _thread.is_alive()):
        return

    def show() -> None:
        try:
            import ctypes

            ctypes.windll.user32.MessageBoxW(
                None,
                "A preparar o teu espaço de aprendizagem local…",
                _TITLE,
                0x00000040 | 0x00010000,
            )
        except (AttributeError, OSError):
            return

    _thread = threading.Thread(target=show, name="aprendix-startup", daemon=True)
    _thread.start()


def close_startup_splash() -> None:
    """Close only the Aprendix startup dialog, leaving the main window intact."""

    if os.name != "nt":
        return
    try:
        import ctypes

        handle = ctypes.windll.user32.FindWindowW("#32770", _TITLE)
        if handle:
            ctypes.windll.user32.PostMessageW(handle, 0x0010, 0, 0)
    except (AttributeError, OSError):
        return
