from datetime import datetime, timezone

UTC = timezone.utc

from aprendix_mobile.completion import MobileCompletion
from aprendix_mobile.notifications import next_review


def test_completion_only_returns_structure_and_declared_symbols() -> None:
    engine = MobileCompletion()
    source = "saldo = 1\nsa"
    assert "saldo" in engine.suggestions(source, len(source))
    assert engine.suggestions("# class", 4) == ()
    assert engine.suggestions("texto = 'def'", 10) == ()
    updated, cursor = engine.insert(source, len(source), "saldo")
    assert updated.endswith("saldo") and cursor == len(updated)


def test_review_schedule_is_local_deterministic_and_privacy_generic() -> None:
    now = datetime(2026, 8, 1, 12, tzinfo=UTC)
    weak = next_review("secret-card-id", mastery=0.1, successful_reviews=0, now=now)
    strong = next_review("secret-card-id", mastery=0.9, successful_reviews=3, now=now)
    assert weak.due_at > now and strong.due_at > weak.due_at
    assert "secret" not in weak.body
