from aprendix.application.tutor_quality import (
    LOCKED_QUESTIONS,
    SUPPORTED_QUESTIONS,
    UNSUPPORTED_QUESTIONS,
)


def test_tutor_quality_suite_has_supported_unknown_and_locked_cases():
    assert len(SUPPORTED_QUESTIONS) >= 12
    assert len(UNSUPPORTED_QUESTIONS) >= 5
    assert len(LOCKED_QUESTIONS) >= 3
    assert len({item.relevant_slug for item in SUPPORTED_QUESTIONS}) == len(SUPPORTED_QUESTIONS)
