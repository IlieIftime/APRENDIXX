# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for the desktop CLI/GUI bundle."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_root = Path(SPECPATH).resolve().parent

datas = collect_data_files(
    "aprendix.presentation",
    includes=["assets/*"],
)
datas += collect_data_files("rapidocr_onnxruntime")
hidden_imports = ["aprendix.bootstrap", *collect_submodules("rapidocr_onnxruntime")]

analysis = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root / "src")],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # HDBSCAN is an explicit post-ingestion build tool. The desktop runtime
    # consumes persisted clusters and does not ship SciPy/scikit-learn.
    excludes=["sklearn", "scipy", "pytest"],
    noarchive=False,
)
python_archive = PYZ(analysis.pure)

executable = EXE(
    python_archive,
    analysis.scripts,
    [],
    name="Aprendix",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    version=str(project_root / "packaging" / "version_info.txt"),
    disable_windowed_traceback=False,
    exclude_binaries=True,
)

collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    name="Aprendix",
)
