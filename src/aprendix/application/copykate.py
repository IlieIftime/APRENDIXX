"""Application service for the local deterministic CopyKate engine."""

from __future__ import annotations

from aprendix.application.contracts import CopyKateRequest, CopyKateResponse
from aprendix.application.copykate_engine import (
    AlternativeSynthesizer,
    EditNGramImitator,
)


class CopyKateService:
    """Learn an edit style and synthesize three explainable alternatives."""

    def __init__(
        self,
        imitator: EditNGramImitator | None = None,
        synthesizer: AlternativeSynthesizer | None = None,
    ) -> None:
        self._imitator = imitator or EditNGramImitator()
        self._synthesizer = synthesizer or AlternativeSynthesizer()

    def generate(self, request: CopyKateRequest) -> CopyKateResponse:
        profile = self._imitator.build_profile(
            request.edits,
            fallback_source=request.source_code,
            order=request.ngram_order,
        )
        alternatives = self._synthesizer.synthesize(
            request.source_code,
            profile,
        )
        return CopyKateResponse(
            profile=profile,
            alternatives=alternatives,
        )
