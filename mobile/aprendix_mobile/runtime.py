"""Mobile-only composition root; it imports no desktop sandbox or clustering."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from aprendix.application.knowledge_structure import PedagogicalReadingAssistant, fold
from aprendix_mobile.completion import MobileCompletion
from aprendix_mobile.execution import RestrictedPython
from aprendix_mobile.haptics import Haptics
from aprendix_mobile.notifications import NotificationScheduler, next_review
from aprendix_mobile.paths import PlatformPaths
from aprendix_mobile.security import HostDevelopmentKeyProvider, device_key_provider
from aprendix_mobile.seed import LiteContentStore, SeedManifest, install_seed
from aprendix_mobile.state import MobileStateStore
from aprendix.application.profile_transfer import read_profile, write_profile
from aprendix.application.snippet_analysis import SnippetAnalyzer
from aprendix_mobile.contracts import SnippetAnalysisDTO
from aprendix_mobile.ocr import MobileOcr
from aprendix.application.game_service import GameBreakService
from aprendix_mobile.game_repository import MobileGameRepository
from aprendix_mobile.cipher import platform_field_cipher
from types import SimpleNamespace
from uuid import UUID


@dataclass(slots=True)
class MobileRuntime:
    paths: PlatformPaths
    content: LiteContentStore
    state: MobileStateStore
    executor: RestrictedPython
    completion: MobileCompletion
    haptics: Haptics
    notifications: NotificationScheduler
    analyzer: SnippetAnalyzer
    ocr: MobileOcr
    games: GameBreakService

    def cards(self, mode: str = "recommended", *, cluster: str | None = None,
              area_id: str | None = None) -> tuple[dict[str, object], ...]:
        cards = list(self.content.cards(area_id=area_id))
        if cluster:
            cards = [item for item in cards if item["cluster_id"] == cluster]
        if mode == "recommended":
            cards.sort(key=lambda item: (self.state.mastery(str(item["id"])), str(item["title"])))
        return tuple(cards)

    def areas(self) -> tuple[dict[str, object], ...]:
        return self.content.areas()

    def courses(self) -> tuple[dict[str, object], ...]:
        return self.content.courses()

    def course_units(self, track_slug: str) -> tuple[dict[str, object], ...]:
        return self.content.course_units(track_slug)

    def complete_unit(self, unit_slug: str) -> None:
        self.state.complete_unit(unit_slug)

    def shortcuts(self, area_id: str | None = None) -> tuple[dict[str, object], ...]:
        return self.content.shortcuts(area_id)

    def sources(self, area_id: str) -> tuple[dict[str, object], ...]:
        return self.content.sources(area_id)

    def search(self, query: str, *, area_id: str | None = None) -> tuple[dict[str, object], ...]:
        return self.content.search(query, area_id=area_id)

    def reading(self, item_id: str, query: str = "") -> dict[str, object]:
        item = self.content.reading_item(item_id)
        summary, simplified, points, math_notes = PedagogicalReadingAssistant.build(
            str(item["body"]), query
        )
        concepts = tuple(
            entry for entry in self.glossary("")
            if fold(str(entry["term"])) in fold(str(item["body"]))
        )[:20]
        return {**item, "summary": summary, "simplified": simplified,
                "key_points": points, "math_notes": math_notes,
                "concepts": concepts}

    def execute(self, exercise_id: str, source: str, expected_output: str | None = None):
        result = self.executor.run(source)
        # Never turn a mere syntax/runtime success into a pedagogical pass.  All
        # packaged exercises carry an independently stored expected result.
        passed = (
            result.status == "ok"
            and expected_output is not None
            and result.stdout.strip() == expected_output.strip()
        )
        self.state.save_attempt(exercise_id, source, result.status, 1.0 if passed else 0.0, result.stdout or result.error_message or "")
        self.haptics.emit("success" if passed else "error")
        return result, passed

    def glossary(self, prefix: str = "") -> tuple[dict[str, str], ...]:
        return self.content.glossary(prefix)

    def grade_quiz(self, item: dict[str, object], option_index: int) -> tuple[bool, str]:
        option_id = chr(ord("a") + option_index)
        passed = option_id == str(item["correct_option"])
        self.state.save_quiz_attempt(
            str(item["quiz_id"]), option_id, passed,
            str(item["explanation"]),
        )
        self.haptics.emit("success" if passed else "error")
        return passed, str(item["explanation"])

    def review_card(self, card_id: str, action: str) -> bool:
        self.state.record_card(card_id, action)
        mastery = self.state.mastery(card_id)
        reminder = next_review(
            card_id, mastery=mastery,
            successful_reviews=max(0, round(mastery * 10)),
        )
        self.haptics.emit("accept")
        return self.notifications.schedule(reminder)

    def export_profile(self, destination: Path, passphrase: str) -> Path:
        return write_profile(destination, passphrase, self.state.export_snapshot())

    def preview_profile(self, source: Path, passphrase: str) -> dict[str, int]:
        return self.state.preview_snapshot(read_profile(source, passphrase))

    def import_profile(self, source: Path, passphrase: str) -> dict[str, int]:
        return self.state.import_snapshot(read_profile(source, passphrase))

    def analyze_snippet(self, request):
        return self.analyzer.analyze(request)

    def extract_image(self, path: Path):
        return self.ocr.extract(path)

    def save_project(
        self, name: str, source: str, *, project_id: str | None = None,
        relative_path: str = "main.py",
    ):
        return self.state.save_project(
            name, source, project_id=project_id, relative_path=relative_path,
        )

    def projects(self):
        return self.state.projects()

    def ask_tutor(self, question: str, *, strategy: str = "explain") -> dict[str, object]:
        clean = question.strip()
        if not 3 <= len(clean) <= 2_000:
            raise ValueError("Escreve uma pergunta entre 3 e 2 000 caracteres.")
        terms = {
            fold(item) for item in re.findall(r"[\w+-]{3,}", clean)
            if fold(item) not in {
                "como", "qual", "quais", "explica", "explicar", "uma", "para",
                "com", "isto", "este", "esta", "funciona", "porque",
            }
        }
        candidates = self.search(clean)
        evidence = []
        for item in candidates[:12]:
            haystack = fold(" ".join(
                str(item.get(key, "")) for key in ("title", "body", "code", "explanation")
            ))
            hits = sum(term in haystack for term in terms)
            if hits >= (1 if len(terms) <= 2 else 2):
                evidence.append(item)
            if len(evidence) >= 3:
                break
        if not evidence:
            return {
                "declined": True, "confidence": 0.0,
                "answer": (
                    "Não encontro evidência local suficiente para responder com rigor. "
                    "Escolhe outro termo, consulta o dicionário ou importa um pack aprovado."
                ),
                "evidence": (),
            }
        primary = evidence[0]
        body = str(primary.get("body") or primary.get("explanation") or primary.get("title"))
        summary, simplified, points, _notes = PedagogicalReadingAssistant.build(body, clean)
        answer = simplified if strategy == "simplify" else summary
        if strategy == "socratic" and points:
            answer += "\n\nPergunta para verificares: como aplicarias este princípio num exemplo mínimo?"
        return {
            "declined": False,
            "confidence": min(.95, .62 + .1 * len(evidence)),
            "answer": answer,
            "evidence": tuple({
                "id": str(item.get("id", "")), "title": str(item.get("title", "Aprendix")),
                "excerpt": str(item.get("body") or item.get("explanation") or "")[:500],
            } for item in evidence),
        }


def build_mobile_runtime(paths: PlatformPaths | None = None, *, allow_host_development: bool = False) -> MobileRuntime:
    paths = paths or PlatformPaths.resolve()
    asset = paths.resources / "knowledge-lite.db"
    manifest = SeedManifest.load(paths.resources / "seed-manifest.json")
    install_seed(asset, manifest, paths.content_database)
    if os.environ.get("ANDROID_ARGUMENT") or os.sys.platform == "ios":
        provider = device_key_provider(paths.data, paths.user_database)
    else:
        provider = HostDevelopmentKeyProvider(
            paths.data / "keys" / "host-development.key",
            database_path=paths.user_database, allow=allow_host_development,
        )
    cipher = platform_field_cipher(provider.get_or_create_key())
    state = MobileStateStore(paths.user_database, cipher)
    return MobileRuntime(
        paths=paths, content=LiteContentStore(paths.content_database),
        state=state,
        executor=RestrictedPython(), completion=MobileCompletion(),
        haptics=Haptics(), notifications=NotificationScheduler(),
        analyzer=SnippetAnalyzer(result_type=SnippetAnalysisDTO), ocr=MobileOcr(),
        games=GameBreakService(
            user=SimpleNamespace(id=UUID("b91edc21-6b54-5d95-881f-f87a02fbded1")),
            repository=MobileGameRepository(state),
        ),
    )
