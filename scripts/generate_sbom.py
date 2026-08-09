"""Generate a deterministic CycloneDX-compatible software bill of materials."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from datetime import UTC, datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("SBOM-1.0.0.json"))
    args = parser.parse_args()
    components = []
    for distribution in sorted(
        importlib.metadata.distributions(),
        key=lambda item: (item.metadata.get("Name", "").casefold(), item.version),
    ):
        name = distribution.metadata.get("Name")
        if not name:
            continue
        components.append(
            {
                "type": "library",
                "name": name,
                "version": distribution.version,
                "purl": f"pkg:pypi/{name.casefold().replace('_', '-')}@{distribution.version}",
            }
        )
    serial_source = json.dumps(components, sort_keys=True, separators=(",", ":"))
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": "urn:uuid:" + hashlib.sha256(serial_source.encode()).hexdigest()[:32],
        "version": 1,
        "metadata": {
            "timestamp": datetime.now(UTC).replace(microsecond=0).isoformat(),
            "component": {"type": "application", "name": "aprendix", "version": "1.0.0"},
        },
        "components": components,
    }
    output = args.output.resolve()
    output.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
