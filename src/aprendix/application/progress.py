"""Bayesian mastery, retention and deterministic personal planning."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from uuid import NAMESPACE_URL, UUID, uuid5

from aprendix.application.contracts import (
    AnalyticsPeriodDTO,
    AnalyticsScope,
    DashboardAnalyticsDTO,
    DashboardIndicatorDTO,
    ErrorCategory,
    EvidenceType,
    LearningAction,
    LearningEvidenceDTO,
    MasteryDistributionDTO,
    MasteryStateDTO,
    MetricDefinitionDTO,
    NextLearningActionDTO,
    PersonalProgressDTO,
    ProgressForecastDTO,
    ProgressSeriesPointDTO,
    TrackAnalyticsDTO,
    WeeklyPlanItemDTO,
    WeeklyProgressReportDTO,
)

FOCUS_MODES = (10, 25, 50, 90)


_ANALYTICS_DEFINITIONS = (
    MetricDefinitionDTO(
        key="mastery", label="Domínio", unit="%",
        definition=(
            "Média do modelo bayesiano de conhecimento no fim do período; "
            "conceitos curriculares ainda sem evidência contribuem com zero."
        ),
        denominator="Todos os nós curriculares no filtro selecionado.",
    ),
    MetricDefinitionDTO(
        key="retention", label="Retenção", unit="%",
        definition=(
            "Probabilidade média de retenção, com decaimento temporal e "
            "meia-vida ampliada por revisões bem-sucedidas."
        ),
        denominator="Todos os nós curriculares no filtro selecionado.",
    ),
    MetricDefinitionDTO(
        key="autonomy", label="Autonomia", unit="%",
        definition=(
            "Independência observada nas respostas, penalizando pistas e "
            "colagem; conceitos sem evidência contribuem com zero."
        ),
        denominator="Todos os nós curriculares no filtro selecionado.",
    ),
    MetricDefinitionDTO(
        key="active_time", label="Tempo ativo", unit="min",
        definition=(
            "Soma do tempo ativo registado; quando indisponível usa a duração "
            "da evidência, comparada com o plano local."
        ),
        denominator="Minutos planeados no mesmo intervalo.",
    ),
    MetricDefinitionDTO(
        key="consistency", label="Consistência", unit="%",
        definition="Proporção de dias do intervalo com pelo menos uma evidência ativa.",
        denominator="Dias decorridos no período selecionado.",
    ),
    MetricDefinitionDTO(
        key="next_milestone", label="Próximo marco", unit="%",
        definition="Exercícios distintos já validados para o próximo marco local.",
        denominator="Quantidade fixa exigida pela definição desse marco.",
    ),
)


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

    def curriculum_node_ids(
        self, *, track_slug: str | None = None,
    ) -> tuple[UUID, ...]:
        """Return the stable denominator used by global dashboard metrics."""

        provider = getattr(self._repository, "analytics_scope_nodes", None)
        if provider is None:
            return tuple(
                node_id for node_id, _title, _difficulty
                in self._repository.node_catalog()
            )
        return tuple(
            item["node_id"] for item in provider(track_slug=track_slug)
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
        today = today or datetime.now(UTC).date()
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
        reference_time = (
            datetime.combine(today, datetime.min.time(), tzinfo=UTC)
            if today is not None else None
        )
        states = self.states(user_id, now=reference_time)
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

    def analytics(
        self,
        user_id: UUID,
        *,
        period_days: int = 30,
        start: datetime | None = None,
        end: datetime | None = None,
        track_slug: str | None = None,
        node_id: UUID | None = None,
        now: datetime | None = None,
    ) -> DashboardAnalyticsDTO:
        """Build daily global/track/node analytics from local numeric evidence.

        State curves are reconstructed with the same BKT/IRT update used when an
        attempt is recorded. This avoids presenting a raw score average as
        knowledge. Global denominators come exclusively from learning chapters.
        """

        if track_slug is not None and node_id is not None:
            raise ValueError("select either a track or a node analytics scope")
        period = self._analytics_period(
            period_days=period_days, start=start, end=end, now=now,
        )
        catalog = self._repository.analytics_scope_nodes(
            track_slug=track_slug, node_id=node_id,
        )
        if not catalog:
            target = track_slug or str(node_id or "global")
            raise ValueError(f"unknown curriculum analytics scope: {target}")
        node_ids = tuple(item["node_id"] for item in catalog)
        evidence = self._repository.analytics_evidence(
            user_id, node_ids, before=period.end,
        )
        planned = self._repository.analytics_planned_minutes(
            user_id, period.start.date(), self._exclusive_end_date(period.end),
        )

        states: dict[UUID, MasteryStateDTO] = {}
        index = 0
        while index < len(evidence) and evidence[index].occurred_at < period.start:
            item = evidence[index]
            states[item.node_id] = update_mastery_state(states.get(item.node_id), item)
            index += 1

        series: list[ProgressSeriesPointDTO] = []
        period_evidence: list[LearningEvidenceDTO] = []
        active_dates: set[date] = set()
        practiced_nodes: set[UUID] = set()
        current_date = period.start.date()
        last_date = (period.end - timedelta(microseconds=1)).date()
        elapsed_days = 0
        while current_date <= last_date:
            midnight = datetime.combine(current_date, datetime.min.time(), tzinfo=UTC)
            bucket_start = max(period.start, midnight)
            bucket_end = min(period.end, midnight + timedelta(days=1))
            bucket: list[LearningEvidenceDTO] = []
            while index < len(evidence) and evidence[index].occurred_at < bucket_end:
                item = evidence[index]
                states[item.node_id] = update_mastery_state(states.get(item.node_id), item)
                if item.occurred_at >= bucket_start:
                    bucket.append(item)
                    period_evidence.append(item)
                    practiced_nodes.add(item.node_id)
                index += 1
            elapsed_days += 1
            if bucket:
                active_dates.add(current_date)
            mastery, retention, autonomy, mastered = self._state_metrics(
                states, node_ids, at=bucket_end,
            )
            attempts = tuple(item for item in bucket if item.evidence_type is not EvidenceType.REVIEW)
            active_seconds = sum(
                max(0, item.active_seconds if item.active_seconds is not None else (item.duration_seconds or 0))
                for item in bucket
            )
            series.append(ProgressSeriesPointDTO(
                occurred_on=current_date,
                mastery=mastery,
                retention=retention,
                autonomy=autonomy,
                consistency=len(active_dates) / elapsed_days,
                active_minutes=active_seconds / 60.0,
                planned_minutes=planned.get(current_date, 0.0),
                evidence_count=len(bucket),
                attempts=len(attempts),
                successes=sum(item.score >= 0.7 for item in attempts),
                failures=sum(item.score < 0.7 for item in attempts),
                practiced_nodes=len(practiced_nodes),
                mastered_nodes=mastered,
            ))
            current_date += timedelta(days=1)

        distribution = self._mastery_distribution(states, node_ids, at=period.end)
        tracks = self._track_analytics(
            catalog, states, period_evidence, at=period.end,
        )
        indicators = self._analytics_indicators(
            user_id, series, planned, distribution,
        )
        scope = (
            AnalyticsScope.NODE if node_id is not None else
            AnalyticsScope.TRACK if track_slug is not None else
            AnalyticsScope.GLOBAL
        )
        scope_id = str(node_id) if node_id is not None else track_slug
        scope_title = (
            str(catalog[0]["title"]) if node_id is not None else
            str(catalog[0]["track_title"]) if track_slug is not None else
            "Progresso global"
        )
        return DashboardAnalyticsDTO(
            user_id=user_id,
            scope=scope,
            scope_id=scope_id,
            scope_title=scope_title,
            period=period,
            indicators=indicators,
            series=tuple(series),
            mastery_distribution=distribution,
            tracks=tracks,
            definitions=_ANALYTICS_DEFINITIONS,
        )

    @staticmethod
    def _analytics_period(
        *, period_days: int, start: datetime | None, end: datetime | None,
        now: datetime | None,
    ) -> AnalyticsPeriodDTO:
        if (start is None) != (end is None):
            raise ValueError("custom analytics requires both start and end")
        if start is not None and end is not None:
            label = "Personalizado"
            return AnalyticsPeriodDTO(start=start, end=end, label=label)
        if period_days not in {7, 30, 90}:
            raise ValueError("period_days must be 7, 30, or 90")
        reference = (now or datetime.now(UTC)).astimezone(UTC)
        first_day = reference.date() - timedelta(days=period_days - 1)
        period_start = datetime.combine(first_day, datetime.min.time(), tzinfo=UTC)
        return AnalyticsPeriodDTO(
            start=period_start, end=reference, label=f"Últimos {period_days} dias",
        )

    @staticmethod
    def _exclusive_end_date(value: datetime) -> date:
        if value.time() == datetime.min.time():
            return value.date()
        return value.date() + timedelta(days=1)

    @staticmethod
    def _state_metrics(
        states: dict[UUID, MasteryStateDTO],
        node_ids: tuple[UUID, ...],
        *,
        at: datetime,
    ) -> tuple[float, float, float, int]:
        denominator = max(1, len(node_ids))
        mastery = 0.0
        retention = 0.0
        autonomy = 0.0
        mastered = 0
        for node_id in node_ids:
            state = states.get(node_id)
            if state is None:
                continue
            current_retention = retention_probability(
                last_practiced_at=state.last_practiced_at,
                successful_reviews=state.successful_reviews,
                now=at,
            )
            mastery += state.p_known
            retention += current_retention
            autonomy += state.autonomy
            mastered += int(state.p_known >= 0.8 and current_retention >= 0.6)
        return (
            _bounded(mastery / denominator),
            _bounded(retention / denominator),
            _bounded(autonomy / denominator),
            mastered,
        )

    @staticmethod
    def _mastery_distribution(
        states: dict[UUID, MasteryStateDTO],
        node_ids: tuple[UUID, ...],
        *,
        at: datetime,
    ) -> MasteryDistributionDTO:
        buckets = defaultdict(int)
        for node_id in node_ids:
            state = states.get(node_id)
            if state is None:
                buckets["untouched"] += 1
                continue
            retention = retention_probability(
                last_practiced_at=state.last_practiced_at,
                successful_reviews=state.successful_reviews,
                now=at,
            )
            if state.p_known >= 0.8 and retention >= 0.6:
                buckets["mastered"] += 1
            elif retention < 0.58:
                buckets["at_risk"] += 1
            elif state.evidence_count <= 1:
                buckets["new"] += 1
            else:
                buckets["consolidating"] += 1
        return MasteryDistributionDTO(**buckets)

    def _track_analytics(
        self,
        catalog: tuple[dict[str, object], ...],
        states: dict[UUID, MasteryStateDTO],
        evidence: list[LearningEvidenceDTO],
        *,
        at: datetime,
    ) -> tuple[TrackAnalyticsDTO, ...]:
        by_track: dict[str, list[dict[str, object]]] = defaultdict(list)
        for item in catalog:
            by_track[str(item["track_slug"])].append(item)
        active_by_node: dict[UUID, int] = defaultdict(int)
        practiced: set[UUID] = set()
        for item in evidence:
            active_by_node[item.node_id] += max(
                0,
                item.active_seconds if item.active_seconds is not None else (item.duration_seconds or 0),
            )
            practiced.add(item.node_id)
        result = []
        for slug, items in by_track.items():
            ids = tuple(item["node_id"] for item in items)
            mastery, retention, autonomy, mastered = self._state_metrics(
                states, ids, at=at,
            )
            result.append(TrackAnalyticsDTO(
                track_slug=slug,
                title=str(items[0]["track_title"]),
                curriculum_nodes=len(ids),
                practiced_nodes=sum(node_id in practiced for node_id in ids),
                mastered_nodes=mastered,
                mastery=mastery,
                retention=retention,
                autonomy=autonomy,
                active_minutes=sum(active_by_node[node_id] for node_id in ids) / 60.0,
            ))
        return tuple(result)

    def _analytics_indicators(
        self,
        user_id: UUID,
        series: list[ProgressSeriesPointDTO],
        planned: dict[date, float],
        distribution: MasteryDistributionDTO,
    ) -> tuple[DashboardIndicatorDTO, ...]:
        latest = series[-1]
        first = series[0]
        total_active = sum(point.active_minutes for point in series)
        total_planned = sum(planned.values())
        midpoint = max(1, len(series) // 2)
        earlier_active = sum(point.active_minutes for point in series[:midpoint]) / midpoint
        later_count = max(1, len(series) - midpoint)
        later_active = sum(point.active_minutes for point in series[midpoint:]) / later_count
        milestone_provider = getattr(self._repository, "analytics_next_milestone", None)
        milestone = milestone_provider(user_id) if milestone_provider else None
        completed = int(milestone["completed"]) if milestone else 1
        required = max(1, int(milestone["required"])) if milestone else 1
        definition = {item.key: item for item in _ANALYTICS_DEFINITIONS}

        def indicator(
            key: str, value: float, *, target: float | None = None,
            delta: float = 0.0, detail: str = "",
        ) -> DashboardIndicatorDTO:
            item = definition[key]
            trend = (
                "improving" if delta > 0.02 else
                "slowing" if delta < -0.02 else
                "starting" if not any(point.evidence_count for point in series) else
                "stable"
            )
            return DashboardIndicatorDTO(
                key=key, label=item.label, value=value, unit=item.unit,
                target_value=target, trend_delta=delta, trend=trend,
                definition=item.definition, denominator=item.denominator,
                detail=detail,
            )

        return (
            indicator("mastery", latest.mastery * 100, delta=latest.mastery - first.mastery),
            indicator("retention", latest.retention * 100, delta=latest.retention - first.retention),
            indicator("autonomy", latest.autonomy * 100, delta=latest.autonomy - first.autonomy),
            indicator(
                "active_time", total_active, target=total_planned,
                delta=later_active - earlier_active,
                detail=f"{total_active:.0f} de {total_planned:.0f} min planeados",
            ),
            indicator(
                "consistency", latest.consistency * 100,
                delta=latest.consistency - first.consistency,
                detail=f"{sum(point.evidence_count > 0 for point in series)} dias ativos",
            ),
            indicator(
                "next_milestone", completed / required * 100, target=100,
                detail=(str(milestone["title"]) if milestone else "Todos os marcos concluídos"),
            ),
        )

    def forecast(self, user_id: UUID, *, today: date | None = None) -> ProgressForecastDTO:
        today = today or datetime.now(UTC).date()
        reference_time = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
        states = self.states(user_id, now=reference_time)
        total = max(0, self._repository.curriculum_node_count())
        mastered = sum(state.p_known >= .8 and state.retention >= .6 for state in states)
        mastered = min(total, mastered)
        remaining = max(0, total - mastered)
        plan = self._repository.study_plan(user_id) or {"weekly_hours": 3.0}
        weekly_hours = max(.5, float(plan["weekly_hours"]))
        velocity = sum(state.velocity for state in states) / max(1, len(states))
        minutes_per_node = max(45.0, 105.0 - 35.0 * velocity)
        capacity = weekly_hours * 60 / minutes_per_node
        weeks = math.ceil(remaining / max(.25, capacity)) if remaining else 0
        confidence_evidence = sum(state.confidence for state in states) / max(1, len(states))
        coverage = min(1.0, len(states) / max(1, total))
        confidence = _bounded(.25 + .5 * confidence_evidence + .25 * coverage)
        return ProgressForecastDTO(
            generated_for=today, total_nodes=total, mastered_nodes=mastered,
            remaining_nodes=remaining, weekly_capacity_nodes=round(capacity, 2),
            weeks_remaining=min(5_200, weeks),
            estimated_completion=today + timedelta(weeks=min(5_200, weeks)),
            confidence=confidence,
            assumptions=(
                f"Ritmo configurado: {weekly_hours:g} h/semana.",
                "A estimativa usa apenas conceitos dos cursos e evidência local.",
                "Pausas prolongadas ou alteração do objetivo recalculam a data.",
            ),
        )

    def weekly_report(self, user_id: UUID, *, today: date | None = None) -> WeeklyProgressReportDTO:
        today = today or datetime.now(UTC).date()
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        current_start = datetime.combine(start, datetime.min.time(), tzinfo=UTC)
        current_end = current_start + timedelta(days=7)
        current = self._repository.period_summary(user_id, current_start, current_end)
        previous = self._repository.period_summary(
            user_id, current_start - timedelta(days=7), current_start,
        )
        completion = self._repository.plan_completion(user_id, start, end)
        current_minutes = round(int(current["active_seconds"]) / 60)
        previous_minutes = round(int(previous["active_seconds"]) / 60)
        if previous_minutes == 0:
            change = 1.0 if current_minutes else 0.0
            trend = "starting"
        else:
            change = max(-10.0, min(10.0, (current_minutes - previous_minutes) / previous_minutes))
            trend = "improving" if change >= .1 else "slowing" if change <= -.2 else "stable"
        progress = self.progress(user_id, today=start)
        highlights = (
            f"{current_minutes} minutos ativos em {int(current['evidence_count'])} evidências.",
            f"Resultado médio observado: {float(current['average_score']):.0%}.",
            f"{progress.mastered_nodes} conceitos dominados; {progress.at_risk_nodes} em risco de esquecimento.",
        )
        recommendations = []
        if progress.at_risk_nodes:
            recommendations.append("Começa por uma revisão espaçada dos conceitos em risco.")
        if float(current["average_score"]) < .7 and int(current["evidence_count"]):
            recommendations.append("Mantém a dificuldade e pede uma pista progressiva antes de repetir.")
        if current_minutes < 60:
            recommendations.append("Reserva pelo menos dois blocos curtos de foco para consolidar o hábito.")
        if not recommendations:
            recommendations.append("Mantém o ritmo e valida a transferência num exercício ou projeto diferente.")
        return WeeklyProgressReportDTO(
            week_start=start, week_end=end, active_minutes=current_minutes,
            evidence_count=int(current["evidence_count"]),
            average_score=float(current["average_score"]),
            planned_items=completion["planned"], completed_items=completion["completed"],
            activity_change=change, trend=trend,
            highlights=highlights, recommendations=tuple(recommendations),
        )

    def complete_plan_item(self, user_id: UUID, item_id: UUID, completed: bool = True) -> bool:
        return self._repository.complete_plan_item(user_id, item_id, completed)
