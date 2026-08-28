"""Reproducible, privacy-safe acceptance gate for Iteration 14."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from aprendix.application.contracts import SmartCorrectionResponseDTO
from aprendix.application.exercise_presentation import build_exercise_brief
from aprendix.application.learning_session import assistance_for_attempt
from aprendix.bootstrap import build_runtime
from aprendix.presentation.gui import LearningGuiController


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "reports" / "ITERATION-14-AUDIT-1.0.0.json"


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="aprendix-iteration14-") as directory:
        runtime = build_runtime(Path(directory))
        controller = LearningGuiController(
            user=runtime.user,
            exercises=runtime.exercises,
            submissions=runtime.submission_service,
            snapshot_provider=lambda: {},
            curriculum=runtime.curriculum,
        )
        journeys = tuple(
            item
            for path in controller.learning_paths()
            for item in controller.course_practice(path["track_slug"])
        )
        sample = journeys[0]["exercise"]
        modes = {
            mode: bool(build_exercise_brief(sample).render(mode).strip())
            for mode in ("simple", "guided", "technical")
        }
        failed = SmartCorrectionResponseDTO(
            score=0.0,
            status="failed",
            syntax_valid=True,
            policy_safe=True,
            feedback=("Falha determinística de auditoria.",),
        )
        stages = [
            assistance_for_attempt(failed, failed_attempts=count).stage.value
            for count in range(1, 5)
        ]
        checks = {
            "practice_journey_present": bool(journeys),
            "all_practices_have_theory": all(
                bool(str(item["theory_body"]).strip()) for item in journeys
            ),
            "all_practices_have_guided_example": all(
                bool(str(item["theory_example"]).strip()) for item in journeys
            ),
            "three_brief_modes_render": all(modes.values()),
            "help_ladder_is_ordered": stages == [
                "location", "concept", "strategy", "analogous_example"
            ],
        }
        report = {
            "iteration": 14,
            "passed": all(checks.values()),
            "checks": checks,
            "metrics": {
                "tracks": len(controller.learning_paths()),
                "practice_steps": len(journeys),
                "theory_linked": sum(
                    bool(str(item["theory_body"]).strip()) for item in journeys
                ),
                "examples_linked": sum(
                    bool(str(item["theory_example"]).strip()) for item in journeys
                ),
                "brief_modes": modes,
                "help_stages": stages,
            },
            "privacy": "temporary anonymous profile; no learner text or identifiers emitted",
        }
        OUTPUT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
