"""Build the generated mobile Lite seed required by local release checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT / "src", ROOT / "mobile"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from aprendix_mobile.seed import build_seed  # noqa: E402


def main() -> int:
    assets = ROOT / "mobile" / "assets"
    manifest = build_seed(
        assets / "knowledge-lite.db",
        assets / "seed-manifest.json",
    )
    print(json.dumps({
        "content_version": manifest.content_version,
        "size_bytes": manifest.size_bytes,
        "sha256": manifest.sha256,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
