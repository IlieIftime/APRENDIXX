"""Mobile-only composition root; it imports no desktop sandbox or clustering."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from aprendix.infrastructure.security import AesGcmFieldCipher
from aprendix.application.knowledge_structure import PedagogicalReadingAssistant, fold
from aprendix_mobile.completion import MobileCompletion
from aprendix_mobile.execution import RestrictedPython
from aprendix_mobile.haptics import Haptics
from aprendix_mobile.notifications import NotificationScheduler, next_review
from aprendix_mobile.paths import PlatformPaths
from aprendix_mobile.security import HostDevelopmentKeyProvider, device_key_provider
from aprendix_mobile.seed import LiteContentStore, SeedManifest, install_seed
from aprendix_mobile.state import MobileStateStore


@dataclass(slots=True)
class MobileRuntime:
    paths: PlatformPaths
    content: LiteContentStore
    state: MobileStateStore
    executor: RestrictedPython
    completion: MobileCompletion
    haptics: Haptics
    notifications: NotificationScheduler

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
    cipher = AesGcmFieldCipher(provider.get_or_create_key())
    return MobileRuntime(
        paths=paths, content=LiteContentStore(paths.content_database),
        state=MobileStateStore(paths.user_database, cipher),
        executor=RestrictedPython(), completion=MobileCompletion(),
        haptics=Haptics(), notifications=NotificationScheduler(),
    )
