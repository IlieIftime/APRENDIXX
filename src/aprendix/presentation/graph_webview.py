"""Render and open the local D3 knowledge-graph document."""

from __future__ import annotations

import json
import tempfile
import webbrowser
from collections.abc import Mapping
from importlib.resources import files
from pathlib import Path
from typing import Any


class GraphDocumentRenderer:
    """Inject graph JSON and the vendored D3 runtime into a local HTML document."""

    def render(self, snapshot: Mapping[str, Any] | Any) -> str:
        if hasattr(snapshot, "model_dump"):
            payload = snapshot.model_dump(mode="json")
        elif isinstance(snapshot, Mapping):
            payload = dict(snapshot)
        else:
            raise TypeError("snapshot must be a mapping or Pydantic model")
        if not isinstance(payload.get("nodes", []), (list, tuple)):
            raise TypeError("snapshot nodes must be a collection")
        if not isinstance(payload.get("edges", []), (list, tuple)):
            raise TypeError("snapshot edges must be a collection")
        payload["nodes"] = [
            self._normalize_node(node) for node in payload.get("nodes", [])
        ]
        payload["edges"] = [
            self._normalize_edge(edge) for edge in payload.get("edges", [])
        ]

        asset_root = files("aprendix.presentation").joinpath("assets")
        template = asset_root.joinpath("graph.html").read_text(encoding="utf-8")
        d3_source = asset_root.joinpath("d3.min.js").read_text(encoding="utf-8")
        graph_json = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).replace("<", "\\u003c")
        return template.replace("__D3_SOURCE__", d3_source).replace(
            "__GRAPH_DATA__",
            graph_json,
        )

    @staticmethod
    def _normalize_node(node: Mapping[str, Any]) -> dict[str, Any]:
        normalized = dict(node)
        statistics = normalized.pop("statistics", None)
        if isinstance(statistics, Mapping):
            if "mastery" in statistics:
                normalized["mastery"] = statistics["mastery"]
            else:
                attempts = int(statistics.get("attempt_count", 0))
                successes = int(statistics.get("success_count", 0))
                normalized["mastery"] = successes / attempts if attempts else 0.0
            normalized.setdefault("attempts", int(statistics.get("attempt_count", 0)))
            normalized.setdefault("successes", int(statistics.get("success_count", 0)))
            normalized.setdefault("failures", int(statistics.get("failure_count", 0)))
            normalized.setdefault("last_practiced_at", statistics.get("last_seen_at"))
        analytics = normalized.pop("analytics", None)
        if isinstance(analytics, Mapping):
            # Period analytics is authoritative for the filtered graph. Keep
            # concise top-level names for both the vendored D3 fallback and Kivy.
            for key in (
                "distinct_exercises", "attempts", "successes", "failures",
                "active_seconds", "hint_count", "retention", "autonomy",
                "success_rate", "trend", "last_practiced_at",
                "recommended_action",
            ):
                if key in analytics:
                    normalized[key] = analytics[key]
            if "mastery" in analytics:
                normalized["mastery"] = analytics["mastery"]
        normalized.setdefault("mastery", 0.0)
        return normalized

    @staticmethod
    def _normalize_edge(edge: Mapping[str, Any]) -> dict[str, Any]:
        normalized = dict(edge)
        if "source_node_id" in normalized:
            normalized["source"] = normalized.pop("source_node_id")
        if "target_node_id" in normalized:
            normalized["target"] = normalized.pop("target_node_id")
        normalized.setdefault("relation_type", "co_occurrence")
        normalized.setdefault("directed", False)
        normalized.setdefault(
            "reason", "Atividade observada em proximidade temporal."
        )
        normalized.setdefault("origin", "behavioral")
        return normalized


def open_graph_view(snapshot: Mapping[str, Any] | Any) -> None:
    """Write the offline graph document and open it in the system browser."""

    html = GraphDocumentRenderer().render(snapshot)
    path = Path(tempfile.gettempdir()) / "aprendix-knowledge-graph.html"
    path.write_text(html, encoding="utf-8")
    if not webbrowser.open_new_tab(path.as_uri()):
        raise RuntimeError("Não foi possível abrir o navegador para mostrar o grafo.")
