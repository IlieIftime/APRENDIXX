"""Application service joining assessments to the adaptive graph."""

from __future__ import annotations

from datetime import UTC, datetime
import unicodedata
from uuid import NAMESPACE_URL, uuid5

from aprendix.application.contracts import EventDTO
from aprendix.domain import EventType


class CurriculumService:
    def __init__(self, *, user, repository, events, web=None) -> None:
        self.user, self._repository, self._events, self._web = user, repository, events, web

    def tracks(self): return self._repository.tracks()
    def units(self, track_slug: str): return self._repository.units(track_slug, self.user.id)
    def glossary(self, term: str, *, limit: int = 8):
        local = list(self._repository.glossary(term, limit=limit))
        normalized = unicodedata.normalize("NFKD", term).encode("ascii", "ignore").decode().casefold().strip()
        exact = any(item.get("normalized_term") == normalized for item in local)
        if exact or not normalized or self._web is None:
            return tuple(local)
        try:
            hits = self._web.search(f"{term} programação definição documentação", max_results=min(3, limit))
            for hit in hits:
                local.append({
                    "id": f"web:{hit.id}", "term": hit.title,
                    "normalized_term": normalized, "technology": "web",
                    "definition": hit.excerpt, "signature": "Correspondência web — validar na fonte",
                    "example": "", "related_terms": (),
                    "references": ((hit.title, hit.source),), "origin": "web",
                })
        except (OSError, TimeoutError, RuntimeError, ValueError) as exc:
            if not local:
                local.append({
                    "id": "offline", "term": term, "normalized_term": normalized,
                    "technology": "offline", "definition":
                    "Não existe ainda uma entrada local e a consulta web não está disponível.",
                    "signature": f"Modo offline: {type(exc).__name__}", "example": "",
                    "related_terms": (), "references": (), "origin": "offline",
                })
        return tuple(local[:limit])
    def assessment(self, item_id: str): return self._repository.assessment(item_id)
    def complete_unit(self, unit_id: str):
        return self._repository.complete_unit(self.user.id, unit_id)

    def answer(self, item_id: str, answer: str, *, duration_seconds=None, mode="training"):
        result = self._repository.grade(
            self.user.id, item_id, answer, duration_seconds=duration_seconds, mode=mode
        )
        event_id = uuid5(NAMESPACE_URL, f"aprendix:assessment:{result['attempt_id']}")
        now = datetime.now(UTC)
        self._events.ingest(EventDTO(
            id=event_id, idempotency_key=event_id, user_id=self.user.id,
            event_type=EventType.ASSESSMENT_EVALUATED,
            payload={
                "assessment_id": item_id,
                "node_id": self._repository.graph_node_for_assessment(item_id),
                "status": "passed" if result["passed"] else "failed",
                "score": result["score"],
            }, occurred_at=now, created_at=now,
        ))
        return result
