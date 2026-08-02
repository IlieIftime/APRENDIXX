# -*- mode: python ; coding: utf-8 -*-
"""Small sibling process used by the one-file desktop IDE sandbox."""

from pathlib import Path

project_root = Path(SPECPATH).resolve().parent

analysis = Analysis(
    [str(project_root / "packaging" / "sandbox_entry.py")],
    pathex=[str(project_root / "src")], binaries=[], datas=[], hiddenimports=[],
    hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["kivy", "cv2", "onnxruntime", "rapidocr_onnxruntime", "sklearn", "scipy", "pytest"],
    noarchive=False,
)
python_archive = PYZ(analysis.pure)
executable = EXE(
    python_archive, analysis.scripts, [],
    name="AprendixSandbox", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=True, console=False, disable_windowed_traceback=False,
    exclude_binaries=True,
)
collection = COLLECT(
    executable, analysis.binaries, analysis.datas,
    strip=False, upx=True, name="AprendixSandbox",
)
