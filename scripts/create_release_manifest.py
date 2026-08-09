"""Create the deterministic checksum manifest for distributable artefacts."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERSION = "1.0.0"


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


def main() -> int:
    local = Path(os.environ["LOCALAPPDATA"])
    installation = local / "Programs" / "Aprendix" / VERSION
    artefacts = {
        "windows_executable": installation / "Aprendix.exe",
        "windows_sandbox": installation / "AprendixSandbox" / "AprendixSandbox.exe",
        "android_apk": ROOT / "dist" / "mobile" / f"Aprendix-{VERSION}-android-arm64-release.apk",
        "sbom": ROOT / f"SBOM-{VERSION}.json",
        "dependency_audit": ROOT / f"DEPENDENCY-AUDIT-{VERSION}.json",
        "ocr_benchmark": ROOT / f"OCR-BENCHMARK-{VERSION}.json",
        "search_benchmark": ROOT / f"SEARCH-BENCHMARK-{VERSION}.json",
        "tutor_benchmark": ROOT / "TUTOR-BENCHMARK-AAA.json",
        "baseline_benchmark": ROOT / f"BASELINE-{VERSION}.json",
        "aaa_audit": ROOT / f"AAA-AUDIT-{VERSION}.json",
        "accessibility_audit": ROOT / f"ACCESSIBILITY-AUDIT-{VERSION}.json",
        "multimodal_benchmark": ROOT / f"MULTIMODAL-BENCHMARK-{VERSION}.json",
        "soak_benchmark": ROOT / f"SOAK-BENCHMARK-{VERSION}.json",
        "validation_report": ROOT / f"VALIDATION-{VERSION}.md",
        "release_notes": ROOT / f"RELEASE-NOTES-{VERSION}.md",
        "threat_model": ROOT / "THREAT-MODEL-1.0.md",
        "recovery_guide": ROOT / "RECOVERY-GUIDE-1.0.md",
        "windows_installer": ROOT / "Instalar-Aprendix.bat",
        "windows_uninstaller": ROOT / "Desinstalar-Aprendix.bat",
        "android_adb_installer": ROOT / "Instalar-Android-ADB.bat",
        "mobile_install_guide": ROOT / "INSTALL-MOBILE.md",
    }
    missing = [str(path) for path in artefacts.values() if not path.is_file()]
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
            for name, path in artefacts.items()
        },
        "directories": {
            "windows_runtime": _directory_record(runtime_directory),
        },
    }
    output = ROOT / f"RELEASE-MANIFEST-{VERSION}.json"
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
