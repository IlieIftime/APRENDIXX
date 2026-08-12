from aprendix.application.editor_support import (
    analyze_complexity,
    apply_quick_fix,
    apply_safe_quick_fixes,
    compare_solutions,
    diagnose_python,
    explain_runtime_error,
    find_replace,
    format_python,
    matching_delimiter,
    organize_imports,
    sanitize_exercise_prompt,
)


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


def test_formatter_imports_find_replace_and_delimiter_tools():
    assert format_python("if True:\n\tprint('x')   \n") == "if True:\n    print('x')\n"
    assert organize_imports("import z\nimport a\n\nprint('x')") == "import a\nimport z\n\nprint('x')"
    replaced, count = find_replace(
        "total subtotal TOTAL", "total", "soma",
        case_sensitive=False, whole_word=True,
    )
    assert replaced == "soma subtotal soma" and count == 2
    assert matching_delimiter("resultado = (1 + [2])", 12) == 20


def test_complexity_and_solution_comparison_are_structural():
    linear = "total = 0\nfor n in dados:\n    total += n"
    nested = "for linha in matriz:\n    for valor in linha:\n        print(valor)"
    assert analyze_complexity(linear)["time"] == "O(n)"
    assert analyze_complexity(nested)["time"] == "O(n^2)"
    comparison = compare_solutions(linear, nested)
    assert 0 <= comparison["text_similarity"] <= 1
    assert "For" in comparison["shared_constructs"]


def test_quick_fixes_apply_only_bounded_unambiguous_changes():
    source = "def f():\n\tprint('x')   \n\ttry:\n\t\tpass\n\texcept:\n\t\tpass\n"
    fixed, count = apply_safe_quick_fixes(source)
    assert count >= 4
    assert "\t" not in fixed
    assert "print('x')   " not in fixed
    assert "except Exception:" in fixed
    assert diagnose_python(fixed) == ()

    mutable = next(
        item for item in diagnose_python("def f(items=[]):\n    return items\n")
        if item.code == "default.mutable"
    )
    unchanged, applied = apply_quick_fix("def f(items=[]):\n    return items\n", mutable)
    assert applied is False
    assert unchanged.startswith("def f(items=[])")


def test_runtime_errors_are_explained_without_revealing_a_solution():
    explanation = explain_runtime_error("IndexError", "list index out of range")
    assert "limites" in explanation
    assert "Como investigar" in explanation
    assert "list index out of range" in explanation
