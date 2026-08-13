"""Packaged-executable transport tests for the isolated grader."""

from aprendix.infrastructure import grading


def test_frozen_executor_routes_to_private_executable_mode(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeProcess:
        returncode = 0

        def communicate(self, payload, timeout):
            captured["input"] = payload
            return b'{"status":"passed","message":"ok"}', b""

    def fake_popen(command, **kwargs):
        captured["command"] = command
        return FakeProcess()

    monkeypatch.setattr(grading.sys, "frozen", True, raising=False)
    monkeypatch.setattr(grading.subprocess, "Popen", fake_popen)

    result = grading.IsolatedGradingExecutor().run_test(
        "class Answer:\n    value = 42",
        "assert Answer.value == 42",
        timeout_ms=1_000,
    )

    assert captured["command"] == [grading.sys.executable, "--aprendix-grader"]
    assert b'"source"' in captured["input"]
    assert result == ("passed", "ok")


def test_packaged_evaluator_supports_classes_and_init() -> None:
    result = grading._evaluate_payload(
        {
            "source": (
                "class Counter:\n"
                "    def __init__(self, value):\n"
                "        self.value = value\n"
                "    def add(self, amount):\n"
                "        return self.value + amount"
            ),
            "test": "counter = Counter(2)\nassert counter.add(3) == 5",
        }
    )

    assert result["status"] == "passed"


def test_packaged_evaluator_exposes_safe_key_error_contract() -> None:
    result = grading._evaluate_payload(
        {
            "source": (
                "def required(mapping, key):\n"
                "    if key not in mapping:\n"
                "        raise KeyError(key)\n"
                "    return mapping[key]"
            ),
            "test": (
                "try:\n"
                "    required({'x': 1}, 'missing')\n"
                "    assert False\n"
                "except KeyError:\n"
                "    pass"
            ),
        }
    )

    assert result["status"] == "passed"
