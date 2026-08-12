"""Deterministic tests for BKT, retention and personal planning."""

from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from aprendix.application.contracts import (
    EvidenceType, LearningEvidenceDTO, MasteryStateDTO,
)
from aprendix.application.progress import (
    LearningProgressService, bkt_update, irt_probability, irt_update, retention_probability,
    update_mastery_state,
)

NOW = datetime(2026, 8, 2, 10, tzinfo=UTC)


def test_bkt_positive_and_negative_evidence_move_probability() -> None:
    assert bkt_update(0.3, 1.0) > 0.3
    assert bkt_update(0.7, 0.0) < 0.7
    assert bkt_update(0.5, 0.5) == pytest.approx(0.5288888888888889)


def test_retention_decay_slows_after_successful_reviews() -> None:
    last = NOW - timedelta(days=8)
    without_reviews = retention_probability(
        last_practiced_at=last, successful_reviews=0, now=NOW
    )
    after_reviews = retention_probability(
        last_practiced_at=last, successful_reviews=4, now=NOW
    )
    assert without_reviews < 0.1
    assert after_reviews > without_reviews


def test_2pl_updates_ability_monotonically_and_respects_discrimination() -> None:
    assert irt_probability(-1.0, 0.0) < 0.5
    correct_low, low_info = irt_update(-1.0, 0.0, 1.0, difficulty=0.0, discrimination=0.5)
    correct_high, high_info = irt_update(-1.0, 0.0, 1.0, difficulty=0.0, discrimination=2.0)
    wrong, _ = irt_update(-1.0, 0.0, 0.0, difficulty=0.0, discrimination=1.0)
    assert correct_low > -1.0 and correct_high > -1.0 and wrong < -1.0
    assert high_info > low_info


def test_mastery_tracks_autonomy_velocity_confidence_and_review_date() -> None:
    user_id, node_id = uuid4(), uuid4()
    state = update_mastery_state(None, LearningEvidenceDTO(
        user_id=user_id, node_id=node_id, source_key="attempt:one",
        evidence_type=EvidenceType.PRACTICE, score=1.0,
        duration_seconds=600, hint_count=0, paste_ratio=0.0,
        occurred_at=NOW,
    ))
    assert state.p_known > 0.5
    assert state.autonomy == 1.0
    assert state.velocity == 1.0
    assert 0 < state.confidence < 1
    assert state.next_review_at == NOW + timedelta(days=2)
    assert state.irt_ability > -1.0
    assert state.irt_information > 0.0


class FakeProgressRepository:
    def __init__(self):
        self.user_id = uuid4()
        self.node_ids = (UUID(int=1), UUID(int=2))
        self.saved = {}
        self.items = ()

    def state(self, user_id, node_id): return self.saved.get(node_id)
    def states(self, user_id): return tuple(self.saved.values())
    def commit_evidence(self, evidence, state):
        if any(getattr(item, "source_key", None) == evidence.source_key for item in []):
            return False
        self.saved[evidence.node_id] = state
        return True
    def node_catalog(self, user_id=None):
        return ((self.node_ids[0], "Fundamentos", -1.0), (self.node_ids[1], "POO", 0.5))
    def study_plan(self, user_id):
        return {"weekly_hours": 2.0, "assessment_percent": 25}
    def replace_week(self, user_id, start, items): self.items = items
    def weekly_plan(self, user_id, start, end): return self.items
    def curriculum_node_count(self): return 2
    def activity_summary(self, user_id): return {"active_seconds": 1800, "total_seconds": 2400}
    def period_summary(self, user_id, start, end):
        if start.date() == date(2026, 8, 3):
            return {"active_seconds": 3600, "evidence_count": 4, "average_score": .8}
        return {"active_seconds": 1800, "evidence_count": 2, "average_score": .65}
    def plan_completion(self, user_id, start, end):
        return {"planned": len(self.items), "completed": 1}
    def complete_plan_item(self, user_id, item_id, completed=True): return True


def test_planner_prioritizes_retention_risk_and_respects_week_budget() -> None:
    repository = FakeProgressRepository()
    repository.saved[repository.node_ids[0]] = MasteryStateDTO(
        user_id=repository.user_id, node_id=repository.node_ids[0],
        p_known=0.9, autonomy=0.9, velocity=0.8, confidence=0.9,
        evidence_count=5, last_practiced_at=NOW - timedelta(days=30),
        successful_reviews=0, next_review_at=NOW - timedelta(days=28), updated_at=NOW,
    )
    service = LearningProgressService(repository)

    action = service.best_next_action(repository.user_id, now=NOW)
    plan = service.build_weekly_plan(repository.user_id, today=date(2026, 8, 3))

    assert action is not None
    assert action.reason_code == "retention_risk"
    assert len(plan) == 5
    assert sum(item.duration_minutes for item in plan) == 125
    assert service.action_for_time(repository.user_id, 10, now=NOW).duration_minutes == 10
    with pytest.raises(ValueError):
        service.action_for_time(repository.user_id, 12, now=NOW)


def test_forecast_and_weekly_report_use_local_evidence_and_study_budget() -> None:
    repository = FakeProgressRepository()
    repository.saved[repository.node_ids[0]] = MasteryStateDTO(
        user_id=repository.user_id, node_id=repository.node_ids[0],
        p_known=.9, retention=.9, autonomy=.8, velocity=.75, confidence=.8,
        evidence_count=5, last_practiced_at=datetime(2026, 8, 2, tzinfo=UTC),
        successful_reviews=3, updated_at=datetime(2026, 8, 2, tzinfo=UTC),
    )
    service = LearningProgressService(repository)
    forecast = service.forecast(repository.user_id, today=date(2026, 8, 3))
    report = service.weekly_report(repository.user_id, today=date(2026, 8, 5))
    assert forecast.total_nodes == 2
    assert forecast.mastered_nodes == 1
    assert forecast.estimated_completion >= date(2026, 8, 3)
    assert report.active_minutes == 60
    assert report.trend == "improving"
    assert report.average_score == pytest.approx(.8)
