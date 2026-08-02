from aprendix.application.editor_support import diagnose_python, sanitize_exercise_prompt


def test_prompt_cleanup_removes_encoding_noise_and_pdf_hyphenation():
    source = "# -*- coding: utf-8 -*-\nCalcula uma transforma-\nção segura.\x00"
    cleaned = sanitize_exercise_prompt(source)
    assert "coding" not in cleaned
    assert "transformação" in cleaned
    assert "\x00" not in cleaned


def test_diagnostics_report_syntax_indentation_and_risky_constructs():
    syntax = diagnose_python("def f():\n  return (")
    assert syntax[0].severity == "erro"
    warnings = diagnose_python("def f(items=[]):\n    try:\n        eval('1')\n    except:\n        pass\n")
    messages = " ".join(item.message for item in warnings)
    assert "mutável" in messages and "eval" in messages and "except" in messages
