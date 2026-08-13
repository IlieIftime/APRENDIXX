import pytest

from aprendix.application.text_normalization import (
    TextDecodingError,
    TextNormalizationService,
    TextProfile,
)
from aprendix.infrastructure.web_search import SafeDuckDuckGoSearch


def test_web_decoding_honours_cp1252_without_replacement_characters() -> None:
    service = TextNormalizationService()
    raw = '<meta charset="windows-1252"><p>Ação custa 20 € — hoje.</p>'.encode("cp1252")
    result = service.decode_web(raw, content_type="text/html; charset=windows-1252")
    assert result.encoding == "windows-1252"
    assert "Ação" in result.text and "€" in result.text and "—" in result.text
    assert "\ufffd" not in result.text


def test_reversible_mojibake_is_repaired_but_original_ocr_is_preserved() -> None:
    service = TextNormalizationService()
    result = service.normalize_ocr("aÃ§Ã£o → resultado", confidence=.61)
    assert result.text == "ação → resultado"
    assert result.original == "aÃ§Ã£o → resultado"
    assert result.repaired_mojibake is True
    assert any("confidence" in warning for warning in result.warnings)


def test_irrecoverable_replacement_character_is_never_deleted() -> None:
    with pytest.raises(TextDecodingError, match="replacement"):
        TextNormalizationService().normalize("valor \ufffd inválido", TextProfile.PROSE)


def test_python_declared_encoding_is_decoded_strictly() -> None:
    raw = "# -*- coding: cp1252 -*-\nnome = 'João'\n".encode("cp1252")
    result = TextNormalizationService().decode_python(raw)
    assert result.encoding == "cp1252"
    assert "João" in result.text


def test_notebook_accepts_utf8_bom_and_rejects_legacy_encoding() -> None:
    service = TextNormalizationService()
    result = service.decode_notebook(b"\xef\xbb\xbf{\"cells\": []}")
    assert result.encoding == "utf-8-sig"
    assert result.text == '{"cells": []}'
    with pytest.raises(TextDecodingError, match="not valid UTF-8"):
        service.decode_notebook('{"nome": "João"}'.encode("cp1252"))


def test_formula_profile_rejects_commands_outside_safe_subset() -> None:
    service = TextNormalizationService()
    assert service.normalize(r"C = C_0 (1 + i)^{n}", TextProfile.FORMULA).text
    with pytest.raises(TextDecodingError, match="unsupported"):
        service.normalize(r"\input{secret.txt}", TextProfile.FORMULA)


def test_web_provider_uses_declared_encoding_without_loss(monkeypatch) -> None:
    pytest.importorskip("bs4")

    class Headers(dict):
        def get_content_type(self):
            return "text/html"

    class Response:
        headers = Headers({"Content-Type": "text/html; charset=windows-1252"})

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def geturl(self):
            return "https://html.duckduckgo.com/html/"

        def read(self, _limit):
            return (
                '<div class="result"><a class="result__a" href="https://example.org/acao">'
                'Ação e €</a><div class="result__snippet">Explicação — sem perda.</div></div>'
            ).encode("cp1252")

    monkeypatch.setattr("urllib.request.urlopen", lambda *_args, **_kwargs: Response())
    result = SafeDuckDuckGoSearch().search("ação", max_results=2)
    assert result[0].title == "Ação e €"
    assert "—" in result[0].excerpt
    assert "\ufffd" not in result[0].excerpt


def test_web_decoder_quarantines_irrecoverable_byte_sequence() -> None:
    with pytest.raises(TextDecodingError, match="without data loss"):
        TextNormalizationService().decode_web(b"\x81\x8d\x8f")
