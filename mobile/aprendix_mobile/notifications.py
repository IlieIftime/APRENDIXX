"""Local spaced-repetition reminder policy and native scheduling adapters."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

UTC = timezone.utc


@dataclass(frozen=True, slots=True)
class ReviewReminder:
    identifier: str
    due_at: datetime
    title: str = "Aprendix"
    body: str = "Tens uma revisão local pronta."


def next_review(card_id: str, *, mastery: float, successful_reviews: int, now: datetime | None = None) -> ReviewReminder:
    now = now or datetime.now(UTC)
    days = 0 if mastery < 0.25 else min(30, max(1, 2 ** min(successful_reviews, 4)))
    due = now + (timedelta(hours=4) if days == 0 else timedelta(days=days))
    return ReviewReminder(f"review-{card_id}", due)


class NotificationScheduler:
    def schedule(self, reminder: ReviewReminder) -> bool:
        epoch_ms = int(reminder.due_at.timestamp() * 1_000)
        try:
            if os.environ.get("ANDROID_ARGUMENT"):
                from jnius import autoclass
                return bool(autoclass("io.aprendix.mobile.AprendixNativeBridge").schedule(
                    reminder.identifier, epoch_ms, reminder.title, reminder.body
                ))
            if sys.platform == "ios":
                from rubicon.objc import ObjCClass
                return bool(ObjCClass("AprendixKeychainBridge").scheduleAt_identifier_title_body_(
                    reminder.due_at.timestamp(), reminder.identifier, reminder.title, reminder.body
                ))
        except (ImportError, RuntimeError):
            return False
        return False
