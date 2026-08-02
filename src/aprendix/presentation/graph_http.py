"""Loopback-only HTTP adapter exposing the local graph snapshot."""

from __future__ import annotations

import threading
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import TracebackType
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from aprendix.application.contracts.graph import GraphSnapshotDTO

SnapshotProvider = Callable[[UUID], GraphSnapshotDTO]


class GraphSnapshotServer:
    """Manage a loopback ``GET /graph/snapshot`` server for local consumers."""

    def __init__(
        self,
        provider: SnapshotProvider,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
    ) -> None:
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("graph endpoint must bind to a loopback host")
        if not 0 <= port <= 65_535:
            raise ValueError("port must be in [0, 65535]")
        self._provider = provider
        self._server = ThreadingHTTPServer(
            (host, port),
            self._handler_type(),
        )
        self._thread: threading.Thread | None = None

    @property
    def host(self) -> str:
        return str(self._server.server_address[0])

    @property
    def port(self) -> int:
        return int(self._server.server_address[1])

    @property
    def url(self) -> str:
        host = f"[{self.host}]" if ":" in self.host else self.host
        return f"http://{host}:{self.port}/graph/snapshot"

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="aprendix-graph-http",
            daemon=True,
        )
        self._thread.start()

    def close(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            self._server.shutdown()
            self._thread.join(timeout=5.0)
        self._server.server_close()
        self._thread = None

    def __enter__(self) -> GraphSnapshotServer:
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _handler_type(self) -> type[BaseHTTPRequestHandler]:
        provider = self._provider

        class SnapshotHandler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                parsed = urlsplit(self.path)
                if parsed.path != "/graph/snapshot":
                    self._json_error(HTTPStatus.NOT_FOUND, "endpoint not found")
                    return
                values = parse_qs(parsed.query)
                raw_user_ids = values.get("user_id", [])
                if len(raw_user_ids) != 1:
                    self._json_error(
                        HTTPStatus.BAD_REQUEST,
                        "exactly one user_id query parameter is required",
                    )
                    return
                try:
                    user_id = UUID(raw_user_ids[0])
                except ValueError:
                    self._json_error(
                        HTTPStatus.BAD_REQUEST,
                        "user_id must be a UUID",
                    )
                    return
                try:
                    snapshot = provider(user_id)
                except LookupError:
                    self._json_error(HTTPStatus.NOT_FOUND, "user not found")
                    return
                payload = snapshot.model_dump_json().encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(payload)

            def do_POST(self) -> None:
                self._json_error(
                    HTTPStatus.METHOD_NOT_ALLOWED,
                    "only GET is supported",
                    allow="GET",
                )

            def _json_error(
                self,
                status: HTTPStatus,
                message: str,
                *,
                allow: str | None = None,
            ) -> None:
                import json

                payload = json.dumps(
                    {"error": message},
                    separators=(",", ":"),
                ).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                if allow is not None:
                    self.send_header("Allow", allow)
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, format: str, *args: object) -> None:
                """Avoid leaking local identifiers into stderr."""

        return SnapshotHandler
