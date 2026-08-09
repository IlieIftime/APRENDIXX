"""Create a consistent, checksummed backup of the local Aprendix profile."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from aprendix.bootstrap import default_data_directory


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=default_data_directory())
    parser.add_argument("--label", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-zA-Z0-9._-]{1,80}", args.label):
        raise SystemExit("invalid backup label")
    data = args.data_dir.expanduser().resolve()
    source = data / "aprendix.db"
    if not source.is_file():
        raise SystemExit(f"database not found: {source}")
    destination = data / "backups" / args.label
    destination.mkdir(parents=True, exist_ok=False)
    database_copy = destination / "aprendix.db"
    with sqlite3.connect(source) as live, sqlite3.connect(database_copy) as backup:
        live.backup(backup)
    key = data / "keys" / "fields.key"
    if key.is_file():
        shutil.copy2(key, destination / "fields.key")
    files = {
        item.name: {"bytes": item.stat().st_size, "sha256": digest(item)}
        for item in destination.iterdir() if item.is_file()
    }
    manifest = {
        "created_at": datetime.now(UTC).isoformat(),
        "source": str(data), "label": args.label, "files": files,
    }
    (destination / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(destination)
    print(files["aprendix.db"]["sha256"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
