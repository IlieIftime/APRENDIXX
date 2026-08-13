"""End-to-end desktop learning workspace facade."""

from __future__ import annotations

import ast
import re
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from aprendix.application.clustering import TaxonomyClassifier
from aprendix.application.content_orchestrator import ContentOrchestrator
from aprendix.application.contracts import (
    CodeEditDTO,
    CopyKateRequest,
    EvaluationReceiptDTO,
    EventDTO,
    ExerciseDTO,
    ExerciseTemplateDTO,
    GenerateExerciseRequest,
    GradingTestCaseDTO,
    HintStage,
    HintTemplateDTO,
    LearningPhase,
    ProjectDTO,
    SandboxRequest,
    SmartCorrectionRequestDTO,
    SmartCorrectionResponseDTO,
    SubmitAttemptCommand,
    TemplateParameterDTO,
)
from aprendix.application.copykate import CopyKateService
from aprendix.application.learning_session import assistance_for_attempt, classify_error
from aprendix.application.mobile import (
    CodeProvenanceGuard,
    EditTelemetry,
    StructuralCompletionEngine,
)
from aprendix.application.remediation import diagnose_correction
from aprendix.application.services import (
    AttemptSubmissionService,
    EventIngestionService,
)
from aprendix.application.worked_solutions import (
    build_reference_walkthrough,
    explain_reference_solution,
    solution_fingerprint,
)
from aprendix.domain import AttemptStatus, EventType


class DesktopLearningService:
    def __init__(
        self, *, user, exercises, submissions: AttemptSubmissionService,
        attempts, events: EventIngestionService, workspace, sandbox, corrector,
        cache=None, progress=None, debugger=None,
    ) -> None:
        self.user = user
        self._exercises = exercises
        self._submissions = submissions
        self._attempts = attempts
        self._events = events
        self._workspace = workspace
        self._sandbox = sandbox
        self._corrector = corrector
        self._cache = cache
        self._progress = progress
        self._debugger = debugger
        self.copykate = CopyKateService()
        self.completion = StructuralCompletionEngine()
        self.provenance = CodeProvenanceGuard()

    def run(self, source_code: str):
        return self._sandbox.run(SandboxRequest(
            source_code=source_code, timeout_ms=2_000,
            memory_limit_mb=192, max_output_bytes=32_768,
        ))

    def debug(self, request, exercise_id: UUID | None = None):
        if self._debugger is None:
            raise RuntimeError("Debugger isolado indisponível.")
        result = self._debugger.debug(request)
        self._workspace.record_debug_session(self.user.id, exercise_id, request, result)
        return result

    def evaluate(
        self, exercise: ExerciseDTO, source_code: str, duration_ms: int, *,
        telemetry: EditTelemetry | None = None, justification: str = "",
        proficiency: float = 0.0, active_seconds: int | None = None,
        response_confidence: float = 0.5,
        hint_count: int = 0, theory_title: str = "", theory_example: str = "",
        evaluation_locked: bool = False,
        transfer_context: bool = False,
    ) -> EvaluationReceiptDTO:
        telemetry = telemetry or EditTelemetry(typed_characters=len(source_code), pasted_characters=0)
        decision = self.provenance.assess(
            telemetry, proficiency=proficiency, prompt=exercise.prompt,
            exercise_id=str(exercise.id),
        )
        if decision.requires_justification and not self.provenance.validate_justification(justification):
            raise ValueError("Esta edição contém uma colagem extensa; explica primeiro a tua abordagem em pelo menos 8 palavras.")
        previous_attempts = tuple(
            item for item in self._attempts.list_for_user(self.user.id, limit=100_000)
            if item.exercise_id == exercise.id
            and item.status in {AttemptStatus.PASSED, AttemptStatus.FAILED, AttemptStatus.ERROR}
        )
        previous_failures = sum(item.status is not AttemptStatus.PASSED for item in previous_attempts)
        command = SubmitAttemptCommand(
            user_id=self.user.id, exercise_id=exercise.id,
            source_code=source_code, duration_ms=max(0, duration_ms),
        )
        submission = self._submissions.submit(command)
        correction, output = self._correct(exercise, source_code)
        public = tuple(item for item in correction.test_outcomes if item.visibility == "public")
        hidden = tuple(item for item in correction.test_outcomes if item.visibility == "hidden")
        self._workspace.record_test_run(
            self.user.id, exercise.id,
            public_passed=sum(item.passed for item in public), public_total=len(public),
            hidden_passed=sum(item.passed for item in hidden), hidden_total=len(hidden),
            coverage_percent=0.0,
            result={
                "status": correction.status, "score": correction.score,
                "outcomes": [item.model_dump(mode="json") for item in correction.test_outcomes],
                "rubric": [item.model_dump(mode="json") for item in correction.rubric],
            },
        )
        passed = correction.status == "passed"
        final_status = AttemptStatus.PASSED if passed else (
            AttemptStatus.ERROR if correction.status == "error" else AttemptStatus.FAILED
        )
        self._attempts.finalize(
            submission.attempt_id, status=final_status, output=output,
            score=correction.score,
        )
        evaluated_id = uuid5(NAMESPACE_URL, f"aprendix:attempt-evaluated:{submission.attempt_id}")
        now = datetime.now(UTC)
        self._events.ingest(EventDTO(
            id=evaluated_id, idempotency_key=evaluated_id,
            user_id=self.user.id, event_type=EventType.ATTEMPT_EVALUATED,
            payload={"attempt_id": str(submission.attempt_id), "exercise_id": str(exercise.id),
                     "status": final_status.value, "score": correction.score},
            occurred_at=now, created_at=now,
        ))
        self._workspace.record_editor_evidence(
            user_id=self.user.id, exercise_id=exercise.id,
            attempt_id=submission.attempt_id,
            typed=telemetry.typed_characters,
            pasted=telemetry.pasted_characters,
            deleted=telemetry.deleted_characters,
            justification=justification,
        )
        _technologies, themes = TaxonomyClassifier.classify(
            f"{exercise.title} {exercise.prompt} {exercise.starter_code}"
        )
        access, credit_awarded, milestone = self._workspace.record_practice_attempt_credit(
            self.user.id, exercise.id, submission.attempt_id,
            passed=passed, theme=themes[0],
        )
        if self._progress is not None:
            total_edits = telemetry.typed_characters + telemetry.pasted_characters
            error_category = classify_error(correction)
            self._progress.record_attempt(
                user_id=self.user.id, node_id=exercise.graph_node_id,
                attempt_id=submission.attempt_id, score=correction.score,
                duration_seconds=max(0, duration_ms // 1000),
                active_seconds=active_seconds,
                hint_count=max(0, hint_count),
                paste_ratio=(telemetry.pasted_characters / total_edits if total_edits else 0.0),
                error_category=error_category, item_difficulty=exercise.difficulty,
                response_confidence=response_confidence,
                transfer_score=correction.score if transfer_context else None,
            )
        else:
            error_category = classify_error(correction)
        failed_attempts = 0 if passed else previous_failures + 1
        previous = previous_attempts[-1] if previous_attempts else None
        remediation = None if passed else diagnose_correction(
            correction,
            current_source=source_code,
            previous_source=previous.source_code if previous else "",
            previous_score=previous.score if previous else None,
        )
        assistance = None if passed else assistance_for_attempt(
            correction,
            failed_attempts=failed_attempts,
            concepts=(
                remediation.prerequisite_terms
                if remediation is not None else tuple(theme.value for theme in themes)
            ),
            theory_title=theory_title,
            worked_example=theory_example,
            evaluation_locked=evaluation_locked,
        )
        reference = (
            self._validated_reference_solution(exercise)
            if not evaluation_locked and (passed or failed_attempts >= 4)
            else None
        )
        reference_walkthrough = (
            build_reference_walkthrough(
                str(reference["solution"]), tuple(exercise.tests)
            )
            if reference is not None else None
        )
        current_session = self._workspace.learning_session(self.user.id, exercise.id)
        session_phase = (
            LearningPhase.REFLECTION if passed else
            LearningPhase.GUIDED_PRACTICE if hint_count else
            LearningPhase.INDEPENDENT_PRACTICE
        )
        self._workspace.save_learning_session(current_session.model_copy(update={
            "phase": session_phase,
            "mode": "evaluation" if evaluation_locked else "training",
            "independent_passed": (
                current_session.independent_passed
                or (passed and hint_count == 0 and not evaluation_locked)
            ),
            "transfer_passed": current_session.transfer_passed or (
                passed and transfer_context and not evaluation_locked
            ),
            "hint_count": max(current_session.hint_count, max(0, hint_count)),
            "active_seconds": max(
                current_session.active_seconds,
                max(0, active_seconds if active_seconds is not None else duration_ms // 1000),
            ),
            "updated_at": datetime.now(UTC),
        }))
        return EvaluationReceiptDTO(
            attempt_id=submission.attempt_id, passed=passed, score=correction.score,
            feedback=correction.feedback, milestone=milestone,
            attempt_number=len(previous_attempts) + 1,
            failed_attempts=failed_attempts,
            error_category=error_category,
            assistance_stage=assistance.stage.value if assistance else "",
            assistance_title=assistance.title if assistance else "",
            assistance=assistance.guidance if assistance else (),
            next_action=assistance.next_action if assistance else "",
            worked_example=assistance.worked_example if assistance else "",
            diagnostic_code=remediation.code.value if remediation else "",
            diagnosis_title=remediation.title if remediation else "",
            diagnosis=remediation.diagnosis if remediation else "",
            prerequisite_terms=remediation.prerequisite_terms if remediation else (),
            remediation_actions=remediation.actions if remediation else (),
            mini_exercise=remediation.mini_exercise if remediation else "",
            improvement=remediation.improvement if remediation else "",
            reference_available=reference is not None,
            reference_solution=str(reference["solution"]) if reference else "",
            reference_explanation=str(reference["explanation"]) if reference else "",
            reference_trace=(reference_walkthrough.steps if reference_walkthrough else ()),
            reference_expected_output=(
                reference_walkthrough.expected_behaviour
                if reference_walkthrough else ()
            ),
            reference_validation_hash=str(reference["validation_hash"]) if reference else "",
            access=access,
            credit_awarded=credit_awarded,
        )

    def learning_session(self, exercise_id: UUID):
        return self._workspace.learning_session(self.user.id, exercise_id)

    def learning_session_summary(self):
        return self._workspace.learning_session_summary(self.user.id)

    def update_learning_session(
        self, exercise_id: UUID, *, phase: LearningPhase | str | None = None,
        theory_viewed: bool | None = None, prediction: str | None = None,
        reflection: str | None = None, hint_count: int | None = None,
        active_seconds: int | None = None, mode: str | None = None,
        transfer_passed: bool | None = None,
    ):
        current = self.learning_session(exercise_id)
        updates = {"updated_at": datetime.now(UTC)}
        if phase is not None:
            updates["phase"] = LearningPhase(phase)
        if theory_viewed is not None:
            updates["theory_viewed"] = theory_viewed
        if prediction is not None:
            updates["prediction"] = prediction.strip()
        if reflection is not None:
            updates["reflection"] = reflection.strip()
        if hint_count is not None:
            updates["hint_count"] = max(current.hint_count, hint_count)
        if active_seconds is not None:
            updates["active_seconds"] = max(current.active_seconds, active_seconds)
        if mode is not None:
            updates["mode"] = mode
        if transfer_passed is not None:
            updates["transfer_passed"] = transfer_passed
        return self._workspace.save_learning_session(current.model_copy(update=updates))

    def _correct(self, exercise: ExerciseDTO, source_code: str) -> tuple[SmartCorrectionResponseDTO, str]:
        expected = []
        for test in exercise.tests:
            match = re.fullmatch(r"stdout equals ['\"](.*)['\"]", test.strip(), re.IGNORECASE)
            if match:
                expected.append(match.group(1))
        if expected:
            execution = self.run(source_code)
            actual = execution.stdout.strip()
            passed = execution.status == "ok" and all(actual == value for value in expected)
            feedback = (
                ("Execução e output validados no subprocesso isolado.",)
                if passed else
                (f"Output esperado: {expected[0]!r}; obtido: {actual!r}.",)
            )
            return SmartCorrectionResponseDTO(
                score=1.0 if passed else 0.0,
                status="passed" if passed else ("error" if execution.status not in {"ok", "output_limit"} else "failed"),
                syntax_valid=execution.error_type != "SyntaxError",
                policy_safe=execution.status != "rejected", feedback=feedback,
            ), actual or (execution.error_message or execution.status)
        executable_tests = []
        for index, raw_test in enumerate(exercise.tests, start=1):
            marker, test = "", raw_test.strip()
            while test.startswith("[") and "]" in test:
                current, test = test[1:].split("]", 1)
                marker += " " + current.lower()
                test = test.lstrip()
            try:
                trusted_tree = ast.parse(test, mode="exec")
                has_assertion = any(
                    isinstance(node, ast.Assert) for node in ast.walk(trusted_tree)
                )
            except SyntaxError:
                has_assertion = False
            if has_assertion:
                visibility = "hidden" if "hidden" in marker else "public"
                kind = "property" if "property" in marker else "example"
                executable_tests.append(GradingTestCaseDTO(
                    name=(f"Caso oculto {index}" if visibility == "hidden" else f"Teste {index}"),
                    code=test, visibility=visibility, kind=kind,
                ))
        _technologies, _themes = TaxonomyClassifier.classify(
            f"{exercise.title} {exercise.prompt} {exercise.starter_code}"
        )
        try:
            objective_tree = re.sub(
                r"\s+", " ", f"{exercise.title} {exercise.prompt} {exercise.starter_code}",
            )
            objective_requires_class = bool(
                re.search(r"\bclass\s+[A-Za-z_]", objective_tree)
            )
        except (TypeError, re.error):
            objective_requires_class = False
        required = ("ClassDef",) if objective_requires_class else ()
        correction = self._corrector.correct(SmartCorrectionRequestDTO(
            source_code=source_code,
            tests=tuple(executable_tests),
            required_constructs=required,
        ))
        return correction, "\n".join(correction.feedback)

    def _validated_reference_solution(self, exercise: ExerciseDTO):
        """Lazily validate trusted catalogue code before it can be disclosed."""

        stored = self._workspace.reference_solution(exercise.id)
        if stored is not None:
            stored_solution = str(stored.get("solution", "")).strip()
            expected = solution_fingerprint(stored_solution, tuple(exercise.tests))
            if stored_solution and str(stored.get("validation_hash", "")) == expected:
                return stored
        candidate = exercise.starter_code.strip()
        if not candidate:
            return None
        fingerprint = solution_fingerprint(candidate, tuple(exercise.tests))
        validation, _output = self._correct(exercise, candidate)
        if validation.status != "passed" or validation.score < 1.0:
            return None
        return self._workspace.save_reference_solution(
            exercise.id,
            solution=candidate,
            explanation=explain_reference_solution(candidate),
            validation_hash=fingerprint,
            validator_version="smart-corrector-v1",
        )

    def variation(self, exercise: ExerciseDTO, *, proficiency: float = 0.0):
        template_id = ("variation-" + exercise.slug)[:80]
        template = ExerciseTemplateDTO(
            id=template_id, graph_node_id=exercise.graph_node_id,
            title="{context}: " + exercise.title,
            prompt="Contexto: {context}.\n\n" + exercise.prompt,
            starter_code=exercise.starter_code, tests=exercise.tests or ("Revisão manual segura",),
            parameters=(TemplateParameterDTO(
                name="context", choices=("Finanças pessoais", "Jogos", "Dados locais", "Automação"),
            ),),
            hints=(
                HintTemplateDTO(stage=HintStage.WORKED_EXAMPLE, guidance=0.9, text="Divide o problema em entrada, transformação e saída."),
                HintTemplateDTO(stage=HintStage.SCAFFOLD, guidance=0.55, text="Escreve primeiro a estrutura e testa um caso simples."),
                HintTemplateDTO(stage=HintStage.CUE, guidance=0.2, text="Revê os nomes e as condições-limite."),
            ),
        )
        generated = ContentOrchestrator((template,)).generate(GenerateExerciseRequest(
            template_id=template_id, proficiency=proficiency,
        ))
        self._workspace.save_generated_exercise(self.user.id, exercise.id, generated)
        return generated

    def copykate_suggestions(self, source_code: str, previous_source: str = ""):
        edits = (CodeEditDTO(before=previous_source, after=source_code),) if previous_source != source_code else ()
        return self.copykate.generate(CopyKateRequest(source_code=source_code, edits=edits))

    def milestones(self):
        return self._workspace.milestone_progress(self.user.id)

    def gamification(self):
        return self._workspace.gamification(self.user.id)

    def review_card(
        self, card_id: UUID, *, known: bool | None = None, feedback: str | None = None,
    ) -> None:
        normalized = feedback or ("already_knew" if known else "review")
        self._workspace.record_card_review(
            self.user.id, card_id, known=known, feedback=normalized,
        )
        if self._progress is not None:
            node_id = self._progress.node_for_card(card_id)
            if node_id is not None:
                self._progress.record_review(
                    user_id=self.user.id, node_id=node_id,
                    review_key=f"card:{card_id}:{uuid4()}",
                    known=normalized in {"already_knew", "useful"},
                )

    def daily_card_ids(self, *, limit: int = 30) -> tuple[UUID, ...]:
        return self._workspace.daily_card_ids(self.user.id, limit=limit)

    def save_project(
        self, name: str, source_code: str, project_id: UUID | None = None, *,
        relative_path: str = "main.py",
    ):
        return self._workspace.save_project(ProjectDTO(
            id=project_id or uuid4(),
            user_id=self.user.id, name=name, source_code=source_code,
            relative_path=relative_path,
        ))

    def projects(self):
        return self._workspace.list_projects(self.user.id)

    def project_files(self, project_id: UUID):
        return self._workspace.project_files(self.user.id, project_id)

    def project_versions(self, project_id: UUID, relative_path: str = "main.py"):
        return self._workspace.project_versions(project_id, relative_path)

    def save_debug_recovery(
        self, exercise_id: UUID, source: str, *, cursor_index: int,
        breakpoints=(), watches=(),
    ) -> None:
        self._workspace.save_debug_recovery(
            self.user.id, exercise_id, source, cursor_index=cursor_index,
            breakpoints=breakpoints, watches=watches,
        )

    def load_debug_recovery(self, exercise_id: UUID):
        return self._workspace.load_debug_recovery(self.user.id, exercise_id)

    def debug_history(self, *, limit: int = 30):
        return self._workspace.debug_history(self.user.id, limit=limit)

    def test_history(self, *, limit: int = 30):
        return self._workspace.test_history(self.user.id, limit=limit)

    def record_focus(self, minutes: int, elapsed_seconds: int, status: str) -> None:
        self._workspace.record_focus(
            self.user.id, minutes=minutes, elapsed_seconds=elapsed_seconds,
            status=status,
        )

    def study_plan(self):
        return self._workspace.study_plan(self.user.id)

    def save_study_plan(self, *, start_date, weekly_hours: float, assessment_percent: int):
        return self._workspace.save_study_plan(
            self.user.id, start_date=start_date, weekly_hours=weekly_hours,
            assessment_percent=assessment_percent,
        )

    def save_draft(self, exercise_id: UUID, source_code: str) -> None:
        if self._cache is not None:
            self._cache.put(
                f"draft:{self.user.id}:{exercise_id}", source_code.encode("utf-8"),
                ttl_seconds=30 * 24 * 60 * 60,
            )

    def load_draft(self, exercise_id: UUID) -> str | None:
        if self._cache is None:
            return None
        payload = self._cache.get(f"draft:{self.user.id}:{exercise_id}")
        return payload.decode("utf-8") if payload is not None else None

    def save_preference(self, name: str, value: str) -> None:
        if self._cache is not None:
            self._cache.put(
                f"preference:{self.user.id}:{name}", value.encode("utf-8"),
                ttl_seconds=10 * 365 * 24 * 60 * 60,
            )

    def load_preference(self, name: str, default: str = "") -> str:
        if self._cache is None:
            return default
        payload = self._cache.get(f"preference:{self.user.id}:{name}")
        return payload.decode("utf-8") if payload is not None else default
