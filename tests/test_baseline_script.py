"""The baseline command must remain reproducible and privacy-safe."""

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_baseline_script_writes_a_complete_private_report(tmp_path: Path) -> None:
    output = tmp_path / "baseline.json"
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "benchmark_baseline.py"),
         "--iterations", "1", "--output", str(output)],
        cwd=ROOT, capture_output=True, text=True, timeout=60, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["database"]["integrity"] == "ok"
    assert report["operations"]["sandbox"]["status"] == "ok"
    assert report["operations"]["search"]["result_count"] > 0
    assert all(value is False for value in report["privacy"].values())
