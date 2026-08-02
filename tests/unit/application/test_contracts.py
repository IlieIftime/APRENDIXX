"""Validation and JSON-boundary tests for internal contracts."""

from datetime import datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from aprendix.application.contracts import AttemptDTO, GraphEdgeDTO, UserDTO
from aprendix.domain import AttemptStatus


def test_contract_json_round_trip_preserves_user() -> None:
    user = UserDTO(display_name="  Ada  ")

    restored = UserDTO.model_validate_json(user.to_json())

    assert restored == user
    assert restored.display_name == "Ada"
    assert '"schema_version":1' in user.to_json()


def test_contract_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError, match="timezone"):
        UserDTO(created_at=datetime(2026, 1, 1))


def test_completed_attempt_requires_submission_timestamp() -> None:
    with pytest.raises(ValidationError, match="submitted_at"):
        AttemptDTO(
            user_id=uuid4(),
            exercise_id=uuid4(),
            status=AttemptStatus.PASSED,
            score=1.0,
        )


def test_graph_edge_rejects_self_reference() -> None:
    node_id = uuid4()
    with pytest.raises(ValidationError, match="same node"):
        GraphEdgeDTO(source_node_id=node_id, target_node_id=node_id)

