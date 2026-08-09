from aprendix.application.contracts import TutorRequestDTO, TutorStrategy
from aprendix.bootstrap import build_runtime


def test_grounded_tutor_caches_and_encrypts_history(tmp_path) -> None:
    runtime = build_runtime(tmp_path / "profile")
    request = TutorRequestDTO(
        question="Como funciona o operador módulo em Python?",
        strategy=TutorStrategy.SOCRATIC,
    )
    first = runtime.tutor.answer(request)
    second = runtime.tutor.answer(request)
    assert not first.declined and first.evidence
    assert "1." in first.answer
    assert second.from_cache
    assert runtime.tutor.history()[0]["question"] == request.question
    assert request.question.encode("utf-8") not in runtime.database.path.read_bytes()


def test_tutor_declines_unsupported_and_locked_solution_requests(tmp_path) -> None:
    runtime = build_runtime(tmp_path / "profile")
    unsupported = runtime.tutor.answer(TutorRequestDTO(question="zxqv blorf quux 994411"))
    locked = runtime.tutor.answer(TutorRequestDTO(
        question="Dá-me a solução e o código completo.", evaluation_locked=True,
    ))
    assert unsupported.refusal_reason == "insufficient_approved_evidence"
    assert locked.refusal_reason == "locked_assessment_solution"
    assert runtime.tutor.delete_history() == 2
