"""Loopback HTTP contract for the graph snapshot."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import uuid4

import pytest

from aprendix.application.contracts.graph import GraphSnapshotDTO
from aprendix.presentation.graph_http import GraphSnapshotServer


def test_get_graph_snapshot_returns_pydantic_json() -> None:
    user_id = uuid4()
    generated_at = datetime(2026, 7, 30, tzinfo=UTC)

    def provider(requested_user_id):
        assert requested_user_id == user_id
        return GraphSnapshotDTO(user_id=user_id, generated_at=generated_at)

    with GraphSnapshotServer(provider) as server:
        with urlopen(
            f"{server.url}?user_id={user_id}",
            timeout=2.0,
        ) as response:
            payload = json.loads(response.read())

    assert response.status == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert payload["user_id"] == str(user_id)
    assert payload["schema_version"] == 1
    assert payload["recommendations"] == []


@pytest.mark.parametrize(
    ("path", "status"),
    (
        ("/graph/snapshot", 400),
        ("/graph/snapshot?user_id=not-a-uuid", 400),
        ("/other", 404),
    ),
)
def test_endpoint_rejects_invalid_requests(path: str, status: int) -> None:
    user_id = uuid4()
    with GraphSnapshotServer(
        lambda _: GraphSnapshotDTO(user_id=user_id)
    ) as server:
        with pytest.raises(HTTPError) as error:
            urlopen(
                f"http://{server.host}:{server.port}{path}",
                timeout=2.0,
            )
    assert error.value.code == status


def test_endpoint_is_read_only() -> None:
    user_id = uuid4()
    with GraphSnapshotServer(
        lambda _: GraphSnapshotDTO(user_id=user_id)
    ) as server:
        request = Request(
            f"{server.url}?user_id={user_id}",
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=2.0)
    assert error.value.code == 405
    assert error.value.headers["Allow"] == "GET"
