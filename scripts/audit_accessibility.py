"""Create a privacy-safe accessibility and DPI release audit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src"
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from aprendix.presentation.design_system import accessibility_matrix  # noqa: E402


def audit() -> dict[str, object]:
    matrix = accessibility_matrix()
    return {
        "audit_version": "1",
        "scope": "automated-token-and-logical-layout",
        "privacy": {"contains_user_data": False},
        **matrix,
        "manual_gates": {
            "screen_reader": "requires-supported-screen-reader-and-toolkit",
            "mixed_monitor_dpi": "requires-multi-monitor-hardware",
            "physical_touch": "requires-android-and-ios-devices",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("ACCESSIBILITY-AUDIT-1.0.0.json"))
    args = parser.parse_args()
    report = audit()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(output)
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
