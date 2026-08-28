"""Fail when the installed Windows runtime differs from its release manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from create_release_manifest import _build_input_record, _directory_record, _sha256


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from aprendix import __version__


def verify(manifest_path: Path) -> tuple[str, ...]:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures = []
    for name, record in payload["files"].items():
        raw = Path(record["path"])
        path = raw if raw.is_absolute() else ROOT / raw
        if not path.is_file():
            failures.append(f"{name}: missing {path}")
            continue
        if path.stat().st_size != int(record["size_bytes"]):
            failures.append(f"{name}: size mismatch")
        if _sha256(path) != str(record["sha256"]):
            failures.append(f"{name}: sha256 mismatch")
    runtime_record = payload["directories"]["windows_runtime"]
    runtime_path = Path(runtime_record["path"])
    current_runtime = _directory_record(runtime_path)
    for field in ("file_count", "size_bytes", "tree_sha256"):
        if current_runtime[field] != runtime_record[field]:
            failures.append(f"windows_runtime: {field} mismatch")
    current_inputs = _build_input_record()
    recorded_inputs = payload["directories"]["build_inputs"]
    if current_inputs["tree_sha256"] != recorded_inputs["tree_sha256"]:
        failures.append("build_inputs: tree_sha256 mismatch")
    return tuple(failures)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "manifest",
        type=Path,
        nargs="?",
        default=ROOT / "reports" / f"RELEASE-MANIFEST-{__version__}.json",
    )
    args = parser.parse_args()
    failures = verify(args.manifest.resolve())
    if failures:
        print("\n".join(failures))
        return 1
    print("Release manifest matches installed runtime and build inputs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
