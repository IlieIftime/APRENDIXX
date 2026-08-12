"""Typed contracts for rights-safe pedagogical documents and card provenance."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from hashlib import sha256
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator

from aprendix.application.contracts.models import ContractModel, NonBlankText, utc_now


def _reject_broken_text(value: str) -> str:
    """Keep replacement glyphs and non-printing controls out of rendered content."""

    if "\ufffd" in value:
        raise ValueError("text contains the Unicode replacement character")
    illegal = [char for char in value if ord(char) < 32 and char not in "\n\t\r"]
    if illegal:
        raise ValueError("text contains unsupported control characters")
    return value


class PedagogicalOwnerType(str, Enum):
    LESSON = "lesson"
    EXERCISE = "exercise"
    PROJECT = "project"
    READING = "reading"
    CARD = "card"
    GLOSSARY = "glossary"
    SOURCE = "source"


class PedagogicalBlockKind(str, Enum):
    TITLE = "title"
    PARAGRAPH = "paragraph"
    LIST = "list"
    CODE = "code"
    SIGNATURE = "signature"
    FORMULA = "formula"
    TABLE = "table"
    IMAGE = "image"
    DIAGRAM = "diagram"
    CALLOUT = "callout"
    REFERENCES = "references"


class CardFormat(str, Enum):
    CONCEPT = "concept"
    FORMULA = "formula"
    COMPARISON = "comparison"
    PITFALL = "pitfall"
    MICROEXAMPLE = "microexample"
    APPLICATION = "application"
    VISUAL = "visual"


class PedagogicalSourceLinkDTO(ContractModel):
    source_id: str = Field(min_length=1, max_length=160)
    position: int = Field(ge=0)
    locator: str = Field(default="", max_length=500)
    rationale: NonBlankText = Field(max_length=500)
    source_version: NonBlankText = Field(default="stable", max_length=160)


class CardSourceLinkDTO(PedagogicalSourceLinkDTO):
    title: str = Field(default="", max_length=500)
    canonical_url: str = Field(default="", max_length=2_000)
    license_note: str = Field(default="", max_length=1_000)


class PedagogicalAssetDTO(ContractModel):
    """Immutable, content-addressed asset authored for Aprendix."""

    id: str = Field(pattern=r"^[0-9a-f]{64}$")
    mime_type: str = Field(pattern=r"^image/(svg\+xml|png|jpeg|webp)$")
    content: bytes = Field(min_length=1, max_length=2_000_000)
    storage_uri: str = Field(pattern=r"^aprendix-asset://[0-9a-f]{64}$")
    byte_size: int = Field(gt=0, le=2_000_000)
    width: int | None = Field(default=None, gt=0, le=16_384)
    height: int | None = Field(default=None, gt=0, le=16_384)
    alt_text: NonBlankText = Field(min_length=3, max_length=1_000)
    provenance: NonBlankText = Field(min_length=3, max_length=1_000)
    license: NonBlankText = Field(min_length=2, max_length=300)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def content_address_is_valid(self) -> PedagogicalAssetDTO:
        digest = sha256(self.content).hexdigest()
        if self.id != digest:
            raise ValueError("asset id must equal the SHA-256 of its content")
        if self.storage_uri != f"aprendix-asset://{digest}":
            raise ValueError("storage_uri must be content-addressed")
        if self.byte_size != len(self.content):
            raise ValueError("byte_size does not match content")
        return self


class _BlockBaseDTO(ContractModel):
    id: str = Field(min_length=1, max_length=200)
    ordinal: int = Field(ge=0)
    provenance: NonBlankText = Field(default="Aprendix original", max_length=1_000)
    license: NonBlankText = Field(default="MIT", max_length=300)


class TitleBlockDTO(_BlockBaseDTO):
    kind: Literal["title"] = "title"
    text: NonBlankText = Field(max_length=500)
    level: int = Field(default=2, ge=1, le=6)

    _text_is_renderable = field_validator("text")(_reject_broken_text)


class ParagraphBlockDTO(_BlockBaseDTO):
    kind: Literal["paragraph"] = "paragraph"
    text: NonBlankText = Field(max_length=30_000)

    _text_is_renderable = field_validator("text")(_reject_broken_text)


class ListBlockDTO(_BlockBaseDTO):
    kind: Literal["list"] = "list"
    items: tuple[NonBlankText, ...] = Field(min_length=1, max_length=100)
    ordered: bool = False

    @field_validator("items")
    @classmethod
    def items_are_renderable(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(_reject_broken_text(item) for item in value)


class CodeBlockDTO(_BlockBaseDTO):
    kind: Literal["code"] = "code"
    language: NonBlankText = Field(default="text", max_length=80)
    code: NonBlankText = Field(max_length=100_000)
    caption: str = Field(default="", max_length=500)

    _code_is_renderable = field_validator("code")(_reject_broken_text)


class SignatureBlockDTO(_BlockBaseDTO):
    kind: Literal["signature"] = "signature"
    signature: NonBlankText = Field(max_length=2_000)
    language: NonBlankText = Field(default="python", max_length=80)
    description: str = Field(default="", max_length=4_000)

    _signature_is_renderable = field_validator("signature")(_reject_broken_text)


class FormulaBlockDTO(_BlockBaseDTO):
    kind: Literal["formula"] = "formula"
    latex: NonBlankText = Field(max_length=10_000)
    spoken: NonBlankText = Field(max_length=5_000)
    variables: dict[str, str] = Field(default_factory=dict, max_length=50)

    @field_validator("latex", "spoken")
    @classmethod
    def formula_is_renderable(cls, value: str) -> str:
        return _reject_broken_text(value)


class TableBlockDTO(_BlockBaseDTO):
    kind: Literal["table"] = "table"
    headers: tuple[NonBlankText, ...] = Field(min_length=1, max_length=30)
    rows: tuple[tuple[str, ...], ...] = Field(default=(), max_length=500)
    caption: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def rows_match_headers(self) -> TableBlockDTO:
        if any(len(row) != len(self.headers) for row in self.rows):
            raise ValueError("every table row must match the header count")
        for cell in (*self.headers, *(cell for row in self.rows for cell in row)):
            _reject_broken_text(cell)
        return self


class ImageBlockDTO(_BlockBaseDTO):
    kind: Literal["image"] = "image"
    asset_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    alt_text: NonBlankText = Field(min_length=3, max_length=1_000)
    caption: str = Field(default="", max_length=1_000)


class DiagramBlockDTO(_BlockBaseDTO):
    kind: Literal["diagram"] = "diagram"
    asset_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    diagram_kind: str = Field(default="concept-map", pattern=r"^[a-z][a-z0-9-]{1,79}$")
    alt_text: NonBlankText = Field(min_length=3, max_length=1_000)
    caption: str = Field(default="", max_length=1_000)


class CalloutBlockDTO(_BlockBaseDTO):
    kind: Literal["callout"] = "callout"
    tone: str = Field(default="note", pattern=r"^(note|tip|warning|example|definition)$")
    title: NonBlankText = Field(max_length=300)
    body: NonBlankText = Field(max_length=10_000)

    @field_validator("title", "body")
    @classmethod
    def callout_is_renderable(cls, value: str) -> str:
        return _reject_broken_text(value)


class ReferencesBlockDTO(_BlockBaseDTO):
    kind: Literal["references"] = "references"
    references: tuple[PedagogicalSourceLinkDTO, ...] = Field(min_length=1, max_length=100)


PedagogicalBlockDTO = Annotated[
    TitleBlockDTO
    | ParagraphBlockDTO
    | ListBlockDTO
    | CodeBlockDTO
    | SignatureBlockDTO
    | FormulaBlockDTO
    | TableBlockDTO
    | ImageBlockDTO
    | DiagramBlockDTO
    | CalloutBlockDTO
    | ReferencesBlockDTO,
    Field(discriminator="kind"),
]


class PedagogicalDocumentDTO(ContractModel):
    id: str = Field(min_length=1, max_length=200)
    owner_type: PedagogicalOwnerType
    owner_id: str = Field(min_length=1, max_length=200)
    title: NonBlankText = Field(max_length=500)
    summary: str = Field(default="", max_length=10_000)
    locale: str = Field(default="pt-PT", pattern=r"^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8})*$")
    version: int = Field(default=1, ge=1)
    provenance: NonBlankText = Field(max_length=1_000)
    license: NonBlankText = Field(max_length=300)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    blocks: tuple[PedagogicalBlockDTO, ...] = Field(default=(), max_length=500)
    sources: tuple[PedagogicalSourceLinkDTO, ...] = Field(default=(), max_length=100)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def document_is_consistent(self) -> PedagogicalDocumentDTO:
        ordinals = [block.ordinal for block in self.blocks]
        if ordinals != list(range(len(ordinals))):
            raise ValueError("block ordinals must be contiguous and ordered from zero")
        positions = [source.position for source in self.sources]
        if positions != list(range(len(positions))):
            raise ValueError("source positions must be contiguous and ordered from zero")
        if len({source.source_id for source in self.sources}) != len(self.sources):
            raise ValueError("document sources must be unique")
        if self.updated_at < self.created_at:
            raise ValueError("updated_at cannot precede created_at")
        return self


class GlossaryExampleDTO(ContractModel):
    id: str = Field(min_length=1, max_length=200)
    entry_id: str = Field(min_length=1, max_length=200)
    ordinal: int = Field(ge=0)
    example: NonBlankText = Field(max_length=20_000)
    explanation: NonBlankText = Field(max_length=10_000)
    difficulty: str = Field(pattern=r"^(beginner|intermediate|advanced)$")
    context: NonBlankText = Field(max_length=160)
    source_id: str | None = Field(default=None, max_length=160)

    @field_validator("example", "explanation")
    @classmethod
    def example_is_renderable(cls, value: str) -> str:
        return _reject_broken_text(value)

