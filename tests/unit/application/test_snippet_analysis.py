import struct

import pytest

from aprendix.application.contracts import (
    OcrRegionDTO,
    SnippetAction,
    SnippetRequestDTO,
)
from aprendix.application.snippet_analysis import SnippetAnalyzer
from aprendix.bootstrap import build_runtime
from aprendix.infrastructure.image_ocr import LocalImageOcr


def test_python_analysis_is_static_structural_and_explainable() -> None:
    result = SnippetAnalyzer().analyze(SnippetRequestDTO(
        text="def total(values):\n    result = 0\n    for value in values:\n        result += value\n    return result",
        action=SnippetAction.CREATE_TESTS,
    ))
    assert result.detected_language == "python"
    assert "FunctionDef" in result.constructs and "For" in result.constructs
    assert result.complexity_time == "O(n)"
    assert len(result.suggested_tests) >= 3
    assert "executou" in result.summary


def test_pseudocode_conversion_preserves_original_and_requires_explicit_use() -> None:
    source = "SE x > 0 ENTAO\nESCREVER x\nFIM"
    result = SnippetAnalyzer().analyze(SnippetRequestDTO(
        text=source, action=SnippetAction.TO_PYTHON,
    ))
    assert result.original == source
    assert result.proposed_code == "if x > 0:\n    print(x)"


def test_snippet_history_is_encrypted_and_deletable(tmp_path) -> None:
    runtime = build_runtime(tmp_path / "profile")
    secret = "ALGORITMO segredo_local_917"
    runtime.snippets.analyze(SnippetRequestDTO(text=secret))
    assert secret.encode() not in runtime.database.path.read_bytes()
    assert runtime.snippets.delete_history() == 1


def test_ocr_rejects_malformed_and_oversized_dimensions(tmp_path) -> None:
    malformed = tmp_path / "bad.png"; malformed.write_bytes(b"not-an-image")
    with pytest.raises(ValueError): LocalImageOcr().extract(malformed)
    huge = b"\x89PNG\r\n\x1a\n" + b"\x00" * 8 + struct.pack(">II", 10000, 10000)
    image = tmp_path / "huge.png"; image.write_bytes(huge)
    with pytest.raises(ValueError, match="25 MP"): LocalImageOcr().extract(image)


def test_ocr_reconstructs_fragments_as_indented_code_lines() -> None:
    regions = [
        OcrRegionDTO(text="def", confidence=.99, box=((10, 10), (70, 10), (70, 40), (10, 40))),
        OcrRegionDTO(text="f(x):", confidence=.99, box=((85, 10), (170, 10), (170, 40), (85, 40))),
        OcrRegionDTO(text="return", confidence=.99, box=((90, 60), (190, 60), (190, 90), (90, 90))),
        OcrRegionDTO(text="x", confidence=.99, box=((205, 60), (225, 60), (225, 90), (205, 90))),
    ]
    assert LocalImageOcr._combine_regions(regions) == "def f(x):\n    return x"


def test_ocr_normalization_preserves_original_and_quarantines_damage() -> None:
    ocr = LocalImageOcr()
    text, status, warnings = ocr._normalize_ocr_text("aÃ§Ã£o → resultado", confidence=.8)
    assert text == "ação → resultado"
    assert status == "repaired"
    assert warnings
    damaged = "valor \ufffd ambíguo"
    text, status, warnings = ocr._normalize_ocr_text(damaged, confidence=.9)
    assert text == damaged
    assert status == "quarantined"
    assert "mantido sem alterações" in warnings[0]


@pytest.mark.parametrize("lossless", [False, True])
def test_ocr_identifies_common_webp_variants(tmp_path, lossless: bool) -> None:
    pillow = pytest.importorskip("PIL.Image")
    path = tmp_path / ("lossless.webp" if lossless else "lossy.webp")
    pillow.new("RGB", (137, 59), "white").save(path, "WEBP", lossless=lossless)
    assert LocalImageOcr._identify(path.read_bytes()) == ("WebP", 137, 59)
