"""End-to-end desktop learning workspace facade."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from aprendix.application.clustering import TaxonomyClassifier
from aprendix.application.contracts import (
    CodeEditDTO, CopyKateRequest, EvaluationReceiptDTO, EventDTO, ExerciseDTO,
    ExerciseTemplateDTO, FadedHintDTO, FallbackReason, GenerateExerciseRequest,
    GradingTestCaseDTO, HintStage, HintTemplateDTO, ProjectDTO, SandboxRequest,
    SmartCorrectionRequestDTO, SmartCorrectionResponseDTO, SubmitAttemptCommand,
    TemplateParameterDTO,
)
from aprendix.application.content_orchestrator import ContentOrchestrator
from aprendix.application.copykate import CopyKateService
from aprendix.application.mobile import CodeProvenanceGuard, EditTelemetry, StructuralCompletionEngine
from aprendix.application.services import AttemptSubmissionService, EventIngestionService
from aprendix.domain import AttemptStatus, EventType


class DesktopLearningService:
    def __init__(
        self, *, user, exercises, submissions: AttemptSubmissionService,
        attempts, events: EventIngestionService, workspace, sandbox, corrector,
        cache=None,
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
        self.copykate = CopyKateService()
        self.completion = StructuralCompletionEngine()
        self.provenance = CodeProvenanceGuard()

    def run(self, source_code: str):
        return self._sandbox.run(SandboxRequest(
            source_code=source_code, timeout_ms=2_000,
            memory_limit_mb=192, max_output_bytes=32_768,
        ))

    def evaluate(
        self, exercise: ExerciseDTO, source_code: str, duration_ms: int, *,
        telemetry: EditTelemetry | None = None, justification: str = "",
        proficiency: float = 0.0,
    ) -> EvaluationReceiptDTO:
        telemetry = telemetry or EditTelemetry(typed_characters=len(source_code), pasted_characters=0)
        decision = self.provenance.assess(
            telemetry, proficiency=proficiency, prompt=exercise.prompt,
            exercise_id=str(exercise.id),
        )
        if decision.requires_justification and not self.provenance.validate_justification(justification):
            raise ValueError("Esta edição contém uma colagem extensa; explica primeiro a tua abordagem em pelo menos 8 palavras.")
        command = SubmitAttemptCommand(
            user_id=self.user.id, exercise_id=exercise.id,
            source_code=source_code, duration_ms=max(0, duration_ms),
        )
        submission = self._submissions.submit(command)
        correction, output = self._correct(exercise, source_code)
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
        self._workspace.record_learning_activity(self.user.id, passed=passed)
        _technologies, themes = TaxonomyClassifier.classify(f"{exercise.title} {exercise.prompt}")
        milestone = self._workspace.record_distinct_pass(
            self.user.id, exercise.id, theme=themes[0]
        ) if passed else None
        if passed:
            self._workspace.complete_practice_unit(self.user.id, exercise.id)
        return EvaluationReceiptDTO(
            attempt_id=submission.attempt_id, passed=passed, score=correction.score,
            feedback=correction.feedback, milestone=milestone,
        )

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
        executable_tests = tuple(
            GradingTestCaseDTO(name=f"Teste {index}", code=test)
            for index, test in enumerate(exercise.tests, start=1)
            if test.lstrip().startswith("assert ")
        )
        _technologies, themes = TaxonomyClassifier.classify(
            f"{exercise.title} {exercise.prompt}"
        )
        required = ("ClassDef",) if any(theme.value == "oop" for theme in themes) else ()
        correction = self._corrector.correct(SmartCorrectionRequestDTO(
            source_code=source_code,
            tests=executable_tests,
            required_constructs=required,
        ))
        return correction, "\n".join(correction.feedback)

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

    def review_card(self, card_id: UUID, *, known: bool) -> None:
        self._workspace.record_card_review(self.user.id, card_id, known=known)

    def save_project(self, name: str, source_code: str, project_id: UUID | None = None):
        return self._workspace.save_project(ProjectDTO(
            id=project_id or uuid4(),
            user_id=self.user.id, name=name, source_code=source_code,
        ))

    def projects(self):
        return self._workspace.list_projects(self.user.id)

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
