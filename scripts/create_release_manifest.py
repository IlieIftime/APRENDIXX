"""Create the deterministic checksum manifest for distributable artefacts."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
DOCS = ROOT / "docs"
REPORTS = ROOT / "reports"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from aprendix import __version__ as VERSION


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _directory_record(path: Path) -> dict[str, object]:
    """Hash file names, sizes and contents for a deterministic runtime tree."""

    files = tuple(sorted(item for item in path.rglob("*") if item.is_file()))
    digest = hashlib.sha256()
    total = 0
    for item in files:
        relative = item.relative_to(path).as_posix()
        size = item.stat().st_size
        total += size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256(item)))
    return {
        "path": str(path),
        "file_count": len(files),
        "size_bytes": total,
        "tree_sha256": digest.hexdigest(),
    }


def _resolve_versioned(path: Path) -> Path:
    """Pick the requested versioned artefact or the newest compatible fallback."""

    if path.is_file():
        return path
    token = VERSION
    if token not in path.name:
        return path
    pattern = path.name.replace(token, "*")
    candidates = sorted(path.parent.glob(pattern))
    return candidates[-1] if candidates else path


def _build_input_record() -> dict[str, object]:
    roots = (ROOT / "src", ROOT / "mobile", ROOT / "packaging", ROOT / "scripts")
    files = [
        item for root in roots if root.is_dir()
        for item in root.rglob("*")
        if item.is_file() and "__pycache__" not in item.parts
    ]
    files.extend(path for path in (ROOT / "main.py", ROOT / "pyproject.toml") if path.is_file())
    digest = hashlib.sha256()
    total = 0
    for item in sorted(set(files)):
        relative = item.relative_to(ROOT).as_posix()
        size = item.stat().st_size
        total += size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(bytes.fromhex(_sha256(item)))
    try:
        revision = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True,
            capture_output=True, text=True, timeout=5,
        ).stdout.strip()
        dirty = bool(subprocess.run(
            ["git", "status", "--porcelain"], cwd=ROOT, check=True,
            capture_output=True, text=True, timeout=10,
        ).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        revision, dirty = None, None
    return {
        "file_count": len(set(files)), "size_bytes": total,
        "tree_sha256": digest.hexdigest(), "git_revision": revision,
        "git_dirty": dirty,
    }


def main() -> int:
    local = Path(os.environ["LOCALAPPDATA"])
    installation = local / "Programs" / "Aprendix" / VERSION
    artefacts = {
        "windows_executable": installation / "Aprendix.exe",
        "windows_sandbox": installation / "AprendixSandbox" / "AprendixSandbox.exe",
        "windows_installation_record": installation / "installation.json",
        "android_apk": ROOT / "dist" / "mobile" / f"Aprendix-{VERSION}-android-arm64-release.apk",
        "sbom": REPORTS / f"SBOM-{VERSION}.json",
        "dependency_audit": REPORTS / f"DEPENDENCY-AUDIT-{VERSION}.json",
        "ocr_benchmark": REPORTS / f"OCR-BENCHMARK-{VERSION}.json",
        "search_benchmark": REPORTS / f"SEARCH-BENCHMARK-{VERSION}.json",
        "tutor_benchmark": REPORTS / "TUTOR-BENCHMARK-AAA.json",
        "baseline_benchmark": REPORTS / f"BASELINE-{VERSION}.json",
        "aaa_audit": REPORTS / f"AAA-AUDIT-{VERSION}.json",
        "iteration_13_audit": REPORTS / "ITERATION-13-AUDIT-1.0.0.json",
        "iteration_14_audit": REPORTS / "ITERATION-14-AUDIT-1.0.0.json",
        "iteration_14_report": DOCS / "legacy" / "iterations" / "ITERATION-14.md",
        "iteration_15_audit": REPORTS / "ITERATION-15-AUDIT-1.0.0.json",
        "iteration_15_report": DOCS / "legacy" / "iterations" / "ITERATION-15.md",
        "iteration_16_audit": REPORTS / "ITERATION-16-AUDIT-1.0.0.json",
        "iteration_16_report": DOCS / "legacy" / "iterations" / "ITERATION-16.md",
        "iteration_17_audit": REPORTS / "ITERATION-17-AUDIT-1.0.0.json",
        "iteration_17_report": DOCS / "legacy" / "iterations" / "ITERATION-17.md",
        "iteration_19_audit": REPORTS / "ITERATION-19-AUDIT-1.0.0.json",
        "iteration_19_report": DOCS / "legacy" / "iterations" / "ITERATION-19.md",
        "iteration_20_audit": REPORTS / "ITERATION-20-AUDIT-1.0.0.json",
        "iteration_20_report": DOCS / "legacy" / "iterations" / "ITERATION-20.md",
        "iteration_21_audit": REPORTS / "ITERATION-21-AUDIT-1.0.0.json",
        "iteration_21_report": DOCS / "legacy" / "iterations" / "ITERATION-21.md",
        "iteration_21_plan": DOCS / "legacy" / "iterations" / "PLAN-ITERATION-21-DESKTOP-BOOK-IDE-INTELLIGENCE.md",
        "accessibility_audit": REPORTS / f"ACCESSIBILITY-AUDIT-{VERSION}.json",
        "multimodal_benchmark": REPORTS / f"MULTIMODAL-BENCHMARK-{VERSION}.json",
        "soak_benchmark": REPORTS / f"SOAK-BENCHMARK-{VERSION}.json",
        "validation_report": DOCS / "releases" / f"VALIDATION-{VERSION}.md",
        "release_notes": DOCS / "releases" / f"RELEASE-NOTES-{VERSION}.md",
        "threat_model": DOCS / "architecture" / "THREAT-MODEL-1.0.md",
        "recovery_guide": DOCS / "guides" / "RECOVERY-GUIDE-1.0.md",
        "windows_installer": ROOT / "Instalar-Aprendix.bat",
        "windows_uninstaller": ROOT / "Desinstalar-Aprendix.bat",
        "android_adb_installer": ROOT / "Instalar-Android-ADB.bat",
        "mobile_install_guide": DOCS / "guides" / "INSTALL-MOBILE.md",
    }
    resolved = {name: _resolve_versioned(path) for name, path in artefacts.items()}
    # A Windows install can be produced without the separately built Android
    # APK (Android requires WSL/Buildozer). Keep that mobile gate in the
    # Android release pipeline, while retaining it in this manifest whenever
    # the artefact is available.
    optional = {"android_apk"}
    missing = [
        str(path) for name, path in resolved.items()
        if name not in optional and not path.is_file()
    ]
    resolved = {
        name: path for name, path in resolved.items()
        if path.is_file() or name not in optional
    }
    runtime_directory = installation / "_internal"
    if not runtime_directory.is_dir():
        missing.append(str(runtime_directory))
    if missing:
        raise FileNotFoundError("Artefactos em falta: " + ", ".join(missing))
    payload = {
        "product": "Aprendix",
        "version": VERSION,
        "generated_at": datetime.now(UTC).isoformat(),
        "files": {
            name: {
                "path": str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path),
                "size_bytes": path.stat().st_size,
                "sha256": _sha256(path),
            }
            for name, path in resolved.items()
        },
        "directories": {
            "windows_runtime": _directory_record(runtime_directory),
            "build_inputs": _build_input_record(),
        },
    }
    output = REPORTS / f"RELEASE-MANIFEST-{VERSION}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
