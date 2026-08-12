"""Offline acceptance gate for the desktop-parity mobile learning journey."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tarfile
import tempfile
import zipfile
from pathlib import Path

from aprendix_mobile.paths import PlatformPaths
from aprendix_mobile.runtime import build_mobile_runtime
from aprendix_mobile.seed import SCHEMA_VERSION, build_seed


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "ITERATION-19-AUDIT-1.0.0.json"
APK = ROOT / "dist" / "mobile" / "Aprendix-1.0.0-android-arm64-release.apk"


def _packaged_seed() -> tuple[dict[str, object], str]:
    with zipfile.ZipFile(APK) as archive:
        private_tar = archive.read("assets/private.tar")
    with tarfile.open(fileobj=io.BytesIO(private_tar)) as bundle:
        manifest_file = bundle.extractfile("mobile/assets/seed-manifest.json")
        database_file = bundle.extractfile("mobile/assets/knowledge-lite.db")
        if manifest_file is None or database_file is None:
            raise RuntimeError("mobile seed is absent from the APK")
        manifest = json.loads(manifest_file.read().decode("utf-8"))
        database_sha256 = hashlib.sha256(database_file.read()).hexdigest()
    return manifest, database_sha256


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aprendix-iteration19-") as directory:
        root = Path(directory)
        assets = root / "assets"
        manifest = build_seed(assets / "knowledge-lite.db", assets / "seed-manifest.json")
        paths = PlatformPaths.resolve(
            user_data_dir=root / "data", cache_dir=root / "cache",
            resources_dir=assets,
        )
        runtime = build_mobile_runtime(paths, allow_host_development=True)
        unit = runtime.prepare_course_unit("resources-and-files")
        runtime.update_learning_note(
            "resources-and-files", prediction="ITERATION19_PRIVATE_PREDICTION",
        )
        encrypted_at_rest = b"ITERATION19_PRIVATE_PREDICTION" not in paths.user_database.read_bytes()
        failed = runtime.execute_course_unit(
            "resources-and-files",
            "def classificar_recurso(descricao):\n    return 'x'",
        )
        protected = runtime.execute_course_unit(
            "resources-and-files",
            "def classificar_recurso(descricao):\n    return None",
            mode="evaluation",
        )
        solution = (
            "def classificar_recurso(descricao):\n"
            "    if descricao == 'cálculo imediato':\n        return 'cpu'\n"
            "    if descricao == 'estado temporário':\n        return 'memoria'\n"
            "    return 'armazenamento'\n"
        )
        passed = runtime.execute_course_unit(
            "resources-and-files", solution, active_seconds=35,
        )
        transfer = runtime.execute_course_unit(
            "resources-and-files", solution, transfer_context=True,
        )
        summary = runtime.state.learning_session_summary()
        connection = sqlite3.connect(assets / "knowledge-lite.db")
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            sources = connection.execute("SELECT count(*) FROM sources").fetchone()[0]
            units = connection.execute("SELECT count(*) FROM learning_units").fetchone()[0]
            glossary = connection.execute("SELECT count(*) FROM glossary").fetchone()[0]
        finally:
            connection.close()
        packaged_manifest, packaged_sha256 = _packaged_seed()
        kivy = (ROOT / "mobile" / "aprendix_mobile" / "app.py").read_text(encoding="utf-8")
        toga = (ROOT / "mobile" / "aprendix_mobile" / "toga_app.py").read_text(encoding="utf-8")
        checks = {
            "seed_schema_integrity_and_catalog": (
                integrity == "ok" and manifest.schema_version == SCHEMA_VERSION == 6
                and sources >= 1_000 and units == 50 and glossary >= 3_000
            ),
            "course_opens_in_builtin_ide": (
                unit["session"]["theory_viewed"] is True
                and "Contextualização" in runtime.course_unit_brief(unit)
            ),
            "prediction_encrypted_at_rest": encrypted_at_rest,
            "attempt_aware_training_diagnosis": (
                failed["passed"] is False
                and failed["assistance_stage"] == "localização"
            ),
            "protected_evaluation": (
                protected["passed"] is False
                and protected["assistance_stage"] == "protegido"
                and "classificar_recurso(" not in protected["diagnosis"]
            ),
            "independent_and_transfer_evidence": (
                passed["passed"] is True and transfer["passed"] is True
                and summary["independent_passes"] == 1
                and summary["transfer_passes"] == 1
            ),
            "android_and_ios_shell_parity": (
                "execute_course_unit" in kivy and "execute_course_unit" in toga
                and "update_learning_note" in kivy and "update_learning_note" in toga
            ),
            "release_apk_contains_current_seed": (
                packaged_manifest == json.loads((assets / "seed-manifest.json").read_text(encoding="utf-8"))
                and packaged_sha256 == manifest.sha256
            ),
        }
        report = {
            "iteration": 19,
            "passed": all(checks.values()),
            "checks": checks,
            "metrics": {
                "schema_version": manifest.schema_version,
                "sources": sources,
                "course_units": units,
                "glossary_entries": glossary,
                "learning_sessions": summary["sessions"],
                "apk_bytes": APK.stat().st_size,
                "apk_sha256": hashlib.sha256(APK.read_bytes()).hexdigest(),
            },
            "privacy": "temporary local profile; report contains aggregate counts only",
            "external_gates": (
                "physical Android touch/offline smoke",
                "macOS/Xcode signed iOS build and physical-device smoke",
            ),
        }
        OUTPUT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
