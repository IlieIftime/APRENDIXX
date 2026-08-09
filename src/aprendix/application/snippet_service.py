"""Use-case facade joining OCR confirmation, structural analysis and history."""

from __future__ import annotations

from pathlib import Path


class SnippetAssistantService:
    def __init__(self, *, user, analyzer, ocr, repository) -> None:
        self.user, self._analyzer, self._ocr, self._repository = user, analyzer, ocr, repository

    def extract_image(self, path: Path):
        return self._ocr.extract(path)

    def analyze(self, request):
        result = self._analyzer.analyze(request)
        self._repository.save(self.user.id, request, result)
        return result

    def delete_history(self) -> int:
        return self._repository.delete(self.user.id)
