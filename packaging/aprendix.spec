# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller specification for the desktop CLI/GUI bundle."""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

project_root = Path(SPECPATH).resolve().parent

datas = collect_data_files(
    "aprendix.presentation",
    includes=["assets/*"],
)
datas += collect_data_files(
    "aprendix.application",
    includes=["official_source_catalog.json"],
)
datas += collect_data_files("rapidocr_onnxruntime")
datas += collect_data_files("matplotlib", includes=["mpl-data/**"])
# The source catalogue introspects this bounded stdlib set at startup.  Listing
# it here makes the same verified catalogue available in the frozen executable
# instead of relying on incidental imports discovered by PyInstaller.
stdlib_catalogue_imports = [
    "abc", "argparse", "array", "ast", "asyncio", "bisect", "calendar",
    "collections", "concurrent.futures", "contextlib", "csv", "dataclasses",
    "datetime", "decimal", "difflib", "email", "enum", "fractions",
    "functools", "hashlib", "heapq", "html", "http", "inspect", "io",
    "itertools", "json", "logging", "math", "operator", "os.path", "pathlib",
    "queue", "random", "re", "secrets", "shlex", "sqlite3", "statistics",
    "string", "subprocess", "tempfile", "textwrap", "threading", "time",
    "timeit", "tokenize", "traceback", "typing", "unittest", "urllib.parse",
    "uuid", "warnings", "weakref",
]
hidden_imports = [
    "aprendix.bootstrap",
    "kivy.graphics.svg",
    "matplotlib.backends.backend_agg",
    "matplotlib.mathtext",
    *stdlib_catalogue_imports,
    *collect_submodules("rapidocr_onnxruntime"),
]

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
