"""Use-case facade joining OCR confirmation, structural analysis and history."""

from __future__ import annotations

from pathlib import Path


class SnippetAssistantService:
    def __init__(self, *, user, analyzer, ocr, repository) -> None:
        self.user, self._analyzer, self._ocr, self._repository = user, analyzer, ocr, repository
        self._pending_ocr_text: str | None = None
        self._pending_ocr_quarantined = False

    def extract_image(self, path: Path):
        draft = self._ocr.extract(path)
        self._pending_ocr_text = draft.text
        self._pending_ocr_quarantined = draft.normalization_status == "quarantined"
        return draft

    def analyze(self, request):
        if self._pending_ocr_text is not None and not request.ocr_confirmed:
            raise ValueError("Confirma ou corrige o texto OCR antes de o analisar.")
        if (
            self._pending_ocr_quarantined
            and request.text == self._pending_ocr_text
        ):
            raise ValueError(
                "O OCR está em quarentena; corrige os caracteres ambíguos antes de continuar."
            )
        result = self._analyzer.analyze(request)
        self._repository.save(self.user.id, request, result)
        self._pending_ocr_text = None
        self._pending_ocr_quarantined = False
        return result

    def delete_history(self) -> int:
        return self._repository.delete(self.user.id)
