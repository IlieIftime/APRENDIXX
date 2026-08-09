"""Bayesian mastery, retention and deterministic personal planning."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from aprendix.application.contracts import (
    ErrorCategory,
    EvidenceType,
    LearningAction,
    LearningEvidenceDTO,
    MasteryStateDTO,
    NextLearningActionDTO,
    PersonalProgressDTO,
    WeeklyPlanItemDTO,
)


FOCUS_MODES = (10, 25, 50, 90)


def _bounded(value: float) -> float:
    return min(1.0, max(0.0, value))


def bkt_update(
    prior: float, score: float, *, learn_rate: float = 0.12,
    slip: float = 0.10, guess: float = 0.20, weight: float = 1.0,
) -> float:
    """Update probability of knowledge using a partial-score BKT observation."""

    prior, score = _bounded(prior), _bounded(score)
    correct_denominator = prior * (1 - slip) + (1 - prior) * guess
    wrong_denominator = prior * slip + (1 - prior) * (1 - guess)
    known_if_correct = prior * (1 - slip) / max(1e-9, correct_denominator)
    known_if_wrong = prior * slip / max(1e-9, wrong_denominator)
    observed = score * known_if_correct + (1 - score) * known_if_wrong
    learned = observed + (1 - observed) * learn_rate * _bounded(weight)
    return _bounded(learned)


def retention_probability(
    *, last_practiced_at: datetime | None, successful_reviews: int,
    now: datetime,
) -> float:
    if last_practiced_at is None:
        return 0.0
    elapsed_days = max(0.0, (now - last_practiced_at).total_seconds() / 86_400)
    half_life_days = min(120.0, 2.0 * (1.75 ** min(8, successful_reviews)))
    return _bounded(2 ** (-elapsed_days / half_life_days))


def irt_probability(theta: float, difficulty: float, discrimination: float = 1.0) -> float:
    """Return the 2PL probability of success with overflow-safe bounds."""

    theta = min(4.0, max(-4.0, theta))
    difficulty = min(4.0, max(-4.0, difficulty))
    discrimination = min(3.0, max(0.25, discrimination))
    exponent = max(-20.0, min(20.0, discrimination * (theta - difficulty)))
    return 1.0 / (1.0 + math.exp(-exponent))


def irt_update(theta: float, information: float, score: float, *,
               difficulty: float, discrimination: float,
               weight: float = 1.0) -> tuple[float, float]:
    """Online 2PL update with a conservative normal prior and bounded steps."""

    probability = irt_probability(theta, difficulty, discrimination)
    item_information = discrimination * discrimination * probability * (1 - probability)
    effective_weight = min(1.5, max(0.1, weight))
    posterior_information = max(0.0, information) + effective_weight * item_information
    gradient = effective_weight * discrimination * (_bounded(score) - probability)
    step = max(-0.75, min(0.75, gradient / max(1.0, posterior_information)))
    return min(4.0, max(-4.0, theta + step)), posterior_information


def update_mastery_state(
    previous: MasteryStateDTO | None,
    evidence: LearningEvidenceDTO,
) -> MasteryStateDTO:
    """Fold one privacy-safe evidence item into all five progress dimensions."""

    previous = previous or MasteryStateDTO(
        user_id=evidence.user_id, node_id=evidence.node_id,
    )
    type_weight = {
        EvidenceType.PRACTICE: 1.0,
        EvidenceType.THEORY: 0.65,
        EvidenceType.HYBRID: 0.90,
        EvidenceType.REVIEW: 0.75,
        EvidenceType.PROJECT: 1.0,
    }[evidence.evidence_type]
    independence = _bounded((1 - evidence.paste_ratio) * (1 - min(0.75, evidence.hint_count * 0.12)))
    effective_score = evidence.score
    if evidence.transfer_score is not None:
        effective_score = 0.8 * effective_score + 0.2 * evidence.transfer_score
    if evidence.project_quality is not None:
        effective_score = 0.75 * effective_score + 0.25 * evidence.project_quality
    error_weight = {
        ErrorCategory.NONE: 1.0,
        ErrorCategory.CONCEPTUAL: 1.15,
        ErrorCategory.SYNTAX: 0.72,
        ErrorCategory.RUNTIME: 0.82,
        ErrorCategory.DISTRACTION: 0.45,
    }[evidence.error_category]
    observation_weight = type_weight * (0.55 + 0.45 * independence) * error_weight
    observation_weight *= 0.75 + 0.5 * evidence.response_confidence
    p_known = bkt_update(
        previous.p_known, effective_score,
        weight=observation_weight,
    )
    theta, irt_information = irt_update(
        previous.irt_ability, previous.irt_information, effective_score,
        difficulty=evidence.item_difficulty,
        discrimination=evidence.item_discrimination,
        weight=observation_weight,
    )
    autonomy_sample = _bounded(effective_score * independence)
    if evidence.transfer_score is not None:
        autonomy_sample = _bounded(0.75 * autonomy_sample + 0.25 * evidence.transfer_score)
    duration = evidence.active_seconds if evidence.active_seconds is not None else evidence.duration_seconds
    velocity_sample = 0.5 if duration is None else _bounded(900 / max(300, duration))
    count = previous.evidence_count + 1
    autonomy = (previous.autonomy * previous.evidence_count + autonomy_sample) / count
    velocity = (previous.velocity * previous.evidence_count + velocity_sample) / count
    successful_reviews = previous.successful_reviews + int(
        evidence.evidence_type is EvidenceType.REVIEW and evidence.score >= 0.7
    )
    bkt_confidence = (1 - math.exp(-count / 4)) * (0.7 + 0.3 * independence)
    irt_confidence = 1 - math.exp(-irt_information / 3)
    confidence = _bounded(0.7 * bkt_confidence + 0.3 * irt_confidence)
    interval_days = min(120, max(1, round(2 * (1.75 ** min(8, successful_reviews)))))
    now = evidence.occurred_at.astimezone(UTC)
    return MasteryStateDTO(
        user_id=evidence.user_id, node_id=evidence.node_id,
        p_known=p_known, retention=1.0, autonomy=autonomy,
        velocity=velocity, confidence=confidence,
        irt_ability=theta, irt_information=irt_information, evidence_count=count,
        successful_reviews=successful_reviews, last_practiced_at=now,
        next_review_at=now + timedelta(days=interval_days), updated_at=now,
    )


class LearningProgressService:
    def __init__(self, repository) -> None:
        self._repository = repository

    def record(self, evidence: LearningEvidenceDTO) -> MasteryStateDTO:
        previous = self._repository.state(evidence.user_id, evidence.node_id)
        state = update_mastery_state(previous, evidence)
        inserted = self._repository.commit_evidence(evidence, state)
        return state if inserted else (
            self._repository.state(evidence.user_id, evidence.node_id) or state
        )

    def backfill_legacy_history(self, user_id: UUID) -> int:
        """Idempotently include numeric history created before schema v16."""
        before = sum(state.evidence_count for state in self._repository.states(user_id))
        for evidence in self._repository.legacy_evidence(user_id):
            self.record(evidence)
        after = sum(state.evidence_count for state in self._repository.states(user_id))
        return max(0, after - before)

    def record_attempt(
        self, *, user_id: UUID, node_id: UUID, attempt_id: UUID,
        score: float, duration_seconds: int, hint_count: int = 0,
        paste_ratio: float = 0.0, active_seconds: int | None = None,
        error_category: ErrorCategory = ErrorCategory.NONE,
        item_difficulty: float = 0.0, item_discrimination: float = 1.0,
        response_confidence: float = 0.5, transfer_score: float | None = None,
    ) -> MasteryStateDTO:
        return self.record(LearningEvidenceDTO(
            user_id=user_id, node_id=node_id,
            source_key=f"attempt:{attempt_id}", evidence_type=EvidenceType.PRACTICE,
            score=score, duration_seconds=duration_seconds,
            active_seconds=active_seconds, hint_count=hint_count, paste_ratio=paste_ratio,
            error_category=error_category, item_difficulty=item_difficulty,
            item_discrimination=item_discrimination,
            response_confidence=response_confidence, transfer_score=transfer_score,
        ))

    def record_assessment(
        self, *, user_id: UUID, node_id: UUID, attempt_id: str,
        kind: str, score: float, duration_seconds: int | None,
    ) -> MasteryStateDTO:
        evidence_type = {
            "theory": EvidenceType.THEORY,
            "hybrid": EvidenceType.HYBRID,
            "project": EvidenceType.PROJECT,
        }.get(kind, EvidenceType.THEORY)
        return self.record(LearningEvidenceDTO(
            user_id=user_id, node_id=node_id,
            source_key=f"assessment:{attempt_id}", evidence_type=evidence_type,
            score=score, duration_seconds=duration_seconds,
        ))

    def record_review(
        self, *, user_id: UUID, node_id: UUID, review_key: str, known: bool,
    ) -> MasteryStateDTO:
        return self.record(LearningEvidenceDTO(
            user_id=user_id, node_id=node_id, source_key=review_key,
            evidence_type=EvidenceType.REVIEW, score=1.0 if known else 0.0,
        ))

    def node_for_card(self, card_id: UUID) -> UUID | None:
        return self._repository.node_for_card(card_id)

    def states(self, user_id: UUID, *, now: datetime | None = None):
        now = (now or datetime.now(UTC)).astimezone(UTC)
        return tuple(
            state.model_copy(update={
                "retention": retention_probability(
                    last_practiced_at=state.last_practiced_at,
                    successful_reviews=state.successful_reviews, now=now,
                )
            })
            for state in self._repository.states(user_id)
        )

    def _ranked_actions(self, user_id: UUID, *, minutes: int, now: datetime):
        states = {state.node_id: state for state in self.states(user_id, now=now)}
        ranked = []
        for node_id, title, _difficulty in self._repository.node_catalog(user_id):
            state = states.get(node_id)
            if state is None or state.evidence_count == 0:
                action, priority, reason = LearningAction.LEARN, 0.72, "new_topic"
                explanation = "Tema ainda sem evidência: começa por uma prática guiada curta."
            elif state.retention < 0.58:
                action = LearningAction.REVIEW
                priority = _bounded(0.75 + (0.58 - state.retention) * 0.4)
                reason, explanation = "retention_risk", "A retenção estimada desceu; uma revisão agora reduz o risco de esquecimento."
            elif state.p_known < 0.78:
                action = LearningAction.PRACTICE
                priority = _bounded(0.55 + (0.78 - state.p_known) * 0.5)
                reason, explanation = "mastery_gap", "A evidência ainda não é consistente; pratica uma variação do mesmo nível."
            elif state.autonomy < 0.65:
                action, priority, reason = LearningAction.PRACTICE, 0.56, "autonomy_gap"
                explanation = "O conhecimento está presente, mas convém resolver com menos pistas."
            else:
                action, priority, reason = LearningAction.ASSESS, 0.42, "ready_to_validate"
                explanation = "O domínio e a retenção estão estáveis; valida-os numa avaliação curta."
            ranked.append(NextLearningActionDTO(
                node_id=node_id, title=title, action=action,
                duration_minutes=max(5, min(180, minutes)), priority=priority,
                reason_code=reason, explanation=explanation,
            ))
        return sorted(ranked, key=lambda item: (-item.priority, item.title.casefold()))

    def best_next_action(
        self, user_id: UUID, *, available_minutes: int = 25,
        now: datetime | None = None,
    ) -> NextLearningActionDTO | None:
        ranked = self._ranked_actions(
            user_id, minutes=available_minutes, now=(now or datetime.now(UTC)),
        )
        return ranked[0] if ranked else None

    def action_for_time(self, user_id: UUID, minutes: int, *,
                        now: datetime | None = None) -> NextLearningActionDTO | None:
        if minutes not in FOCUS_MODES:
            raise ValueError("Escolhe 10, 25, 50 ou 90 minutos.")
        return self.best_next_action(user_id, available_minutes=minutes, now=now)

    def build_weekly_plan(
        self, user_id: UUID, *, today: date | None = None,
    ) -> tuple[WeeklyPlanItemDTO, ...]:
        today = today or date.today()
        plan = self._repository.study_plan(user_id)
        weekly_minutes = round(float(plan["weekly_hours"]) * 60) if plan else 180
        assessment_percent = int(plan["assessment_percent"]) if plan else 20
        block = 25 if weekly_minutes < 300 else 50
        count = max(1, min(14, math.ceil(weekly_minutes / block)))
        ranked = self._ranked_actions(
            user_id, minutes=block,
            now=datetime.combine(today, datetime.min.time(), tzinfo=UTC),
        )
        if not ranked:
            return ()
        items = []
        for index in range(count):
            chosen = ranked[index % len(ranked)]
            scheduled = today + timedelta(days=index % 7)
            action = (
                LearningAction.ASSESS
                if assessment_percent and ((index + 1) * 100 // count) <= assessment_percent
                else chosen.action
            )
            item_id = uuid5(
                NAMESPACE_URL,
                f"aprendix:weekly:{user_id}:{scheduled}:{chosen.node_id}:{action.value}",
            )
            items.append(WeeklyPlanItemDTO(
                id=item_id, user_id=user_id, scheduled_for=scheduled,
                node_id=chosen.node_id, title=chosen.title, action=action,
                duration_minutes=block, reason_code=chosen.reason_code,
            ))
        self._repository.replace_week(user_id, today, tuple(items))
        return self._repository.weekly_plan(user_id, today, today + timedelta(days=6))

    def progress(self, user_id: UUID, *, today: date | None = None) -> PersonalProgressDTO:
        states = self.states(user_id)
        plan = self.build_weekly_plan(user_id, today=today)
        denominator = len(states) or 1
        average = lambda name: sum(getattr(state, name) for state in states) / denominator
        activity = (
            self._repository.activity_summary(user_id)
            if hasattr(self._repository, "activity_summary")
            else {"active_seconds": 0, "total_seconds": 0}
        )
        return PersonalProgressDTO(
            mastery=average("p_known"), retention=average("retention"),
            autonomy=average("autonomy"), velocity=average("velocity"),
            confidence=average("confidence"),
            irt_ability=average("irt_ability") if states else -1.0,
            active_minutes=round(activity["active_seconds"] / 60),
            total_minutes=round(activity["total_seconds"] / 60),
            new_nodes=sum(state.evidence_count <= 1 for state in states),
            consolidating_nodes=sum(1 < state.evidence_count and state.p_known < 0.8 for state in states),
            mastered_nodes=sum(state.p_known >= 0.8 and state.retention >= 0.6 for state in states),
            at_risk_nodes=sum(state.evidence_count > 0 and state.retention < 0.58 for state in states),
            next_action=self.best_next_action(user_id), weekly_plan=plan,
        )
