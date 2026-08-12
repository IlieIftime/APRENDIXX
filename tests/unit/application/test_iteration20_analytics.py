"""Iteration 20 dashboard analytics and bounded semantic graph contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from aprendix.application.contracts import (
    EvidenceType,
    GraphRelationType,
    LearningEvidenceDTO,
)
from aprendix.application.progress import LearningProgressService

NOW = datetime(2026, 8, 12, 12, tzinfo=UTC)


class AnalyticsRepository:
    def __init__(self) -> None:
        self.nodes = (UUID(int=1), UUID(int=2))
        self.items = (
            LearningEvidenceDTO(
                user_id=UUID(int=9), node_id=self.nodes[0],
                source_key="attempt:before", evidence_type=EvidenceType.PRACTICE,
                score=0.7, duration_seconds=300, active_seconds=240,
                occurred_at=NOW - timedelta(days=10),
            ),
            LearningEvidenceDTO(
                user_id=UUID(int=9), node_id=self.nodes[0],
                source_key="attempt:current", evidence_type=EvidenceType.PRACTICE,
                score=1.0, duration_seconds=600, active_seconds=480,
                occurred_at=NOW - timedelta(days=2),
            ),
        )

    def analytics_scope_nodes(self, *, track_slug=None, node_id=None):
        items = (
            {"node_id": self.nodes[0], "title": "Valores", "track_slug": "python",
             "track_title": "Python"},
            {"node_id": self.nodes[1], "title": "Condições", "track_slug": "python",
             "track_title": "Python"},
        )
        if track_slug is not None:
            return items if track_slug == "python" else ()
        if node_id is not None:
            return tuple(item for item in items if item["node_id"] == node_id)
        return items

    def analytics_evidence(self, user_id, node_ids, *, before):
        return tuple(
            item for item in self.items
            if item.user_id == user_id and item.node_id in node_ids
            and item.occurred_at < before
        )

    def analytics_planned_minutes(self, user_id, start, end):
        result = {}
        current = start
        while current < end:
            result[current] = 30.0
            current += timedelta(days=1)
        return result

    def analytics_next_milestone(self, user_id):
        return {"title": "bases · apprentice", "completed": 2, "required": 5}


def test_analytics_has_six_defined_indicators_and_curriculum_denominator() -> None:
    service = LearningProgressService(AnalyticsRepository())
    result = service.analytics(UUID(int=9), period_days=7, now=NOW)

    assert result.scope.value == "global"
    assert len(result.series) == 7
    assert len(result.indicators) == 6
    assert {item.key for item in result.indicators} == {
        "mastery", "retention", "autonomy", "active_time",
        "consistency", "next_milestone",
    }
    assert result.series[-1].active_minutes == 0
    assert sum(point.active_minutes for point in result.series) == 8
    # The untouched second curriculum node remains in the global denominator.
    assert 0 < result.series[-1].mastery < 0.5
    assert sum(result.mastery_distribution.model_dump(exclude={"schema_version"}).values()) == 2
    assert result.tracks[0].curriculum_nodes == 2
    assert result.indicators[-1].value == 40
    assert all(item.definition and item.denominator for item in result.indicators)


def test_analytics_supports_track_node_and_bounded_custom_periods() -> None:
    service = LearningProgressService(AnalyticsRepository())
    custom = service.analytics(
        UUID(int=9), start=NOW - timedelta(days=3), end=NOW,
        node_id=UUID(int=1),
    )
    track = service.analytics(UUID(int=9), track_slug="python", period_days=30, now=NOW)

    assert custom.scope.value == "node"
    assert custom.scope_title == "Valores"
    # A midday-to-midday custom window touches four calendar-day buckets.
    assert len(custom.series) == 4
    assert track.scope.value == "track"
    assert len(track.series) == 30
    with pytest.raises(ValueError, match="both start and end"):
        service.analytics(UUID(int=9), start=NOW - timedelta(days=3))
    with pytest.raises(ValueError, match="unknown curriculum"):
        service.analytics(UUID(int=9), track_slug="missing", now=NOW)
    with pytest.raises(ValueError, match="either a track or a node"):
        service.analytics(
            UUID(int=9), track_slug="python", node_id=UUID(int=1), now=NOW,
        )


def test_graph_relationship_enum_is_explicit() -> None:
    assert {item.value for item in GraphRelationType} == {
        "prerequisite", "progression", "related", "co_occurrence",
    }
