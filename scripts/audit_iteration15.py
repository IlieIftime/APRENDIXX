"""Privacy-safe acceptance gate for the adaptive IDE learning loop."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from aprendix.bootstrap import build_runtime


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "ITERATION-15-AUDIT-1.0.0.json"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aprendix-iteration15-") as directory:
        runtime = build_runtime(Path(directory))
        exercise = next(
            item for item in runtime.exercises.list_all() if item.slug == "hello-python"
        )
        session = runtime.desktop.update_learning_session(
            exercise.id,
            phase="independent_practice",
            theory_viewed=True,
            prediction="private-audit-prediction",
            reflection="private-audit-reflection",
            active_seconds=20,
        )
        failures = tuple(
            runtime.desktop.evaluate(exercise, "def quebrada(:\n    pass", 50)
            for _index in range(4)
        )
        pass_receipt = runtime.desktop.evaluate(
            exercise, exercise.starter_code, 60_000, active_seconds=60
        )
        transfer_receipt = runtime.desktop.evaluate(
            exercise,
            exercise.starter_code,
            60_000,
            active_seconds=60,
            transfer_context=True,
        )
        summary = runtime.desktop.learning_session_summary()

        with runtime.database.read_connection() as connection:
            protected = connection.execute(
                "SELECT prediction_encrypted,reflection_encrypted FROM learning_sessions LIMIT 1"
            ).fetchone()
            reference = connection.execute(
                "SELECT solution_encrypted,validation_hash FROM exercise_reference_solutions LIMIT 1"
            ).fetchone()
            assessment_count = int(connection.execute(
                "SELECT count(*) FROM assessment_items"
            ).fetchone()[0])

        raw_session = bytes(protected[0]) + bytes(protected[1])
        raw_reference = bytes(reference[0]) if reference else b""
        checks = {
            "objective_session_resumable": bool(
                session.objective_id and session.objective_code and session.theory_viewed
            ),
            "learner_notes_encrypted": (
                b"private-audit-prediction" not in raw_session
                and b"private-audit-reflection" not in raw_session
            ),
            "diagnosis_is_attempt_aware": (
                [item.failed_attempts for item in failures] == [1, 2, 3, 4]
                and failures[0].diagnostic_code == "syntax"
                and bool(failures[-1].remediation_actions)
            ),
            "reference_is_validated_and_encrypted": bool(
                failures[-1].reference_available
                and failures[-1].reference_validation_hash
                and failures[-1].reference_solution.encode("utf-8") not in raw_reference
            ),
            "independent_and_transfer_evidence": bool(
                pass_receipt.passed
                and transfer_receipt.passed
                and summary["independent_passes"] >= 1
                and summary["transfer_passes"] >= 1
            ),
            "step_assessments_seeded": assessment_count >= 100,
        }
        report = {
            "iteration": 15,
            "passed": all(checks.values()),
            "checks": checks,
            "metrics": {
                "schema_version": runtime.platform.health().schema_version,
                "assessment_items": assessment_count,
                "failed_attempts_exercised": len(failures),
                "sessions": summary["sessions"],
                "independent_passes": summary["independent_passes"],
                "transfer_passes": summary["transfer_passes"],
            },
            "privacy": "aggregate results only; learner notes and code are omitted",
        }
        OUTPUT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
