from types import SimpleNamespace
from uuid import uuid4

import pytest

from aprendix.application.contracts import OcrDraftDTO, SnippetRequestDTO
from aprendix.application.snippet_service import SnippetAssistantService


class FakeOcr:
    def __init__(self, draft):
        self.draft = draft

    def extract(self, _path):
        return self.draft


class FakeAnalyzer:
    def analyze(self, request):
        return SimpleNamespace(text=request.text)


class FakeRepository:
    def __init__(self):
        self.saved = []

    def save(self, user_id, request, result):
        self.saved.append((user_id, request, result))


def service_for(draft):
    repository = FakeRepository()
    service = SnippetAssistantService(
        user=SimpleNamespace(id=uuid4()),
        analyzer=FakeAnalyzer(),
        ocr=FakeOcr(draft),
        repository=repository,
    )
    return service, repository


def test_pending_ocr_must_be_explicitly_confirmed(tmp_path) -> None:
    draft = OcrDraftDTO(text="x = 1", original_text="x = 1", confidence=.98)
    service, repository = service_for(draft)
    assert service.extract_image(tmp_path / "image.png") == draft
    with pytest.raises(ValueError, match="Confirma"):
        service.analyze(SnippetRequestDTO(text="x = 1", ocr_confirmed=False))
    result = service.analyze(SnippetRequestDTO(text="x = 1", ocr_confirmed=True))
    assert result.text == "x = 1"
    assert len(repository.saved) == 1


def test_quarantined_ocr_requires_a_real_correction(tmp_path) -> None:
    damaged = "value = '\ufffd'"
    draft = OcrDraftDTO(
        text=damaged,
        original_text=damaged,
        confidence=.7,
        normalization_status="quarantined",
        warnings=("Corrige o carácter.",),
    )
    service, repository = service_for(draft)
    service.extract_image(tmp_path / "image.png")
    with pytest.raises(ValueError, match="quarentena"):
        service.analyze(SnippetRequestDTO(text=damaged, ocr_confirmed=True))
    result = service.analyze(SnippetRequestDTO(text="value = 'ok'", ocr_confirmed=True))
    assert result.text == "value = 'ok'"
    assert len(repository.saved) == 1
