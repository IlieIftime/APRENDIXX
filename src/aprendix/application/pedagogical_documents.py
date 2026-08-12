"""Normalization, structured pedagogy and deterministic rights-safe visuals."""

from __future__ import annotations

import html
import json
import os
import re
import tempfile
import unicodedata
from collections import Counter
from collections.abc import Iterable
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from aprendix.application.contracts.models import utc_now
from aprendix.application.contracts.pedagogy import (
    CalloutBlockDTO,
    CodeBlockDTO,
    FormulaBlockDTO,
    ListBlockDTO,
    ParagraphBlockDTO,
    PedagogicalAssetDTO,
    PedagogicalBlockDTO,
    PedagogicalDocumentDTO,
    PedagogicalOwnerType,
    PedagogicalSourceLinkDTO,
    SignatureBlockDTO,
    TableBlockDTO,
    TitleBlockDTO,
)

# Form feed (0x0c) remains until page-margin analysis has run.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0e-\x1f\x7f]")
_SOFT_HYPHEN_RE = re.compile("\u00ad")
_LOWER_LETTER = "a-zà-öø-ÿ"
_DEHYPHENATE_RE = re.compile(
    rf"(?<=[{_LOWER_LETTER}])[-‐]\s*\n\s*(?=[{_LOWER_LETTER}])",
    re.IGNORECASE,
)
_LIST_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+(.+)$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
_SIGNATURE_RE = re.compile(
    r"^(?:(?:async\s+)?def\s+[A-Za-z_]\w*\s*\([^\n]*\)(?:\s*->\s*[^:]+)?\s*:|"
    r"class\s+[A-Za-z_]\w*(?:\([^\n]*\))?\s*:)$"
)


def _canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _stable_id(*parts: object) -> str:
    payload = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return sha256(payload).hexdigest()


def normalize_pedagogical_text(
    text: str,
    *,
    preserve_code: bool = False,
    remove_repeated_margins: bool = True,
) -> str:
    """Normalize OCR/PDF text conservatively without changing code semantics.

    Page headers and footers are removed only when the same short line occurs in
    the margin of at least two pages. Dehyphenation is disabled for code.
    """

    if not isinstance(text, str):
        raise TypeError("pedagogical text must be a string")
    value = unicodedata.normalize("NFKC", text.replace("\ufeff", ""))
    value = value.replace("\ufffd", "")
    value = _SOFT_HYPHEN_RE.sub("", value)
    value = _CONTROL_RE.sub("", value)
    value = value.replace("\r\n", "\n").replace("\r", "\n")

    pages = value.split("\f")
    if remove_repeated_margins and len(pages) >= 2:
        candidates: Counter[str] = Counter()
        page_lines: list[list[str]] = []
        for page in pages:
            lines = [line.rstrip() for line in page.splitlines()]
            page_lines.append(lines)
            nonblank = [line.strip() for line in lines if line.strip()]
            for line in {*nonblank[:2], *nonblank[-2:]}:
                if 1 <= len(line) <= 120:
                    candidates[line] += 1
        threshold = max(2, (len(pages) + 1) // 2)
        repeated = {line for line, count in candidates.items() if count >= threshold}
        if repeated:
            pages = [
                "\n".join(line for line in lines if line.strip() not in repeated)
                for lines in page_lines
            ]
    value = "\n\n".join(pages)

    if not preserve_code:
        value = _DEHYPHENATE_RE.sub("", value)
        value = re.sub(r"[ \t]+", " ", value)
        value = re.sub(r"[ \t]*\n[ \t]*", "\n", value)
    else:
        value = "\n".join(line.rstrip() for line in value.splitlines())
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def block_plain_text(block: PedagogicalBlockDTO) -> str:
    kind = block.kind
    if kind == "title":
        return block.text
    if kind == "paragraph":
        return block.text
    if kind == "list":
        return "\n".join(block.items)
    if kind == "code":
        return f"{block.caption}\n{block.code}".strip()
    if kind == "signature":
        return f"{block.signature}\n{block.description}".strip()
    if kind == "formula":
        variables = " ".join(f"{key}: {value}" for key, value in block.variables.items())
        return f"{block.spoken}\n{block.latex}\n{variables}".strip()
    if kind == "table":
        return "\n".join(
            (" | ".join(block.headers), *(" | ".join(row) for row in block.rows))
        )
    if kind in {"image", "diagram"}:
        return f"{block.alt_text}\n{block.caption}".strip()
    if kind == "callout":
        return f"{block.title}\n{block.body}"
    if kind == "references":
        return "\n".join(
            f"{reference.source_id} {reference.locator} {reference.rationale}"
            for reference in block.references
        )
    raise ValueError(f"unsupported block kind: {kind}")


def block_fingerprint(block: PedagogicalBlockDTO) -> str:
    return sha256(
        _canonical_json(block.model_dump(mode="json", exclude={"schema_version"})).encode("utf-8")
    ).hexdigest()


def legacy_text_to_blocks(
    text: str,
    *,
    document_id: str,
    provenance: str = "Aprendix original",
    license_name: str = "MIT",
) -> tuple[PedagogicalBlockDTO, ...]:
    """Convert legacy prose into renderable semantic blocks deterministically."""

    normalized = normalize_pedagogical_text(text)
    if not normalized:
        return ()
    lines = normalized.splitlines()
    raw: list[tuple[str, object]] = []
    index = 0
    paragraph: list[str] = []

    def flush_paragraph() -> None:
        if paragraph:
            raw.append(("paragraph", " ".join(paragraph).strip()))
            paragraph.clear()

    while index < len(lines):
        line = lines[index].strip()
        if not line:
            flush_paragraph()
            index += 1
            continue
        if line.startswith("```"):
            flush_paragraph()
            language = line[3:].strip() or "text"
            index += 1
            code_lines: list[str] = []
            while index < len(lines) and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index < len(lines):
                index += 1
            raw.append(("code", (language, normalize_pedagogical_text(
                "\n".join(code_lines), preserve_code=True
            ))))
            continue
        heading = _HEADING_RE.match(line)
        if heading:
            flush_paragraph()
            raw.append(("title", (len(heading.group(1)), heading.group(2))))
            index += 1
            continue
        if line.startswith("$$"):
            flush_paragraph()
            formula_lines = [line.removeprefix("$$")]
            while not formula_lines[-1].endswith("$$") and index + 1 < len(lines):
                index += 1
                formula_lines.append(lines[index].strip())
            latex = " ".join(formula_lines).removesuffix("$$").strip()
            raw.append(("formula", latex))
            index += 1
            continue
        if _SIGNATURE_RE.fullmatch(line):
            flush_paragraph()
            raw.append(("signature", line))
            index += 1
            continue
        listed = _LIST_RE.match(line)
        if listed:
            flush_paragraph()
            items: list[str] = []
            ordered = bool(re.match(r"^\s*\d", lines[index]))
            while index < len(lines):
                match = _LIST_RE.match(lines[index].strip())
                if match is None:
                    break
                items.append(match.group(1).strip())
                index += 1
            raw.append(("list", (ordered, tuple(items))))
            continue
        if line.count("|") >= 2 and index + 1 < len(lines):
            separator = lines[index + 1].strip()
            if re.fullmatch(r"\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)+\|?", separator):
                flush_paragraph()
                headers = tuple(cell.strip() for cell in line.strip("|").split("|"))
                index += 2
                rows: list[tuple[str, ...]] = []
                while index < len(lines) and lines[index].count("|") >= 2:
                    row = tuple(cell.strip() for cell in lines[index].strip().strip("|").split("|"))
                    if len(row) == len(headers):
                        rows.append(row)
                    index += 1
                raw.append(("table", (headers, tuple(rows))))
                continue
        callout = re.match(
            r"^(Nota|Dica|Atenção|Exemplo|Definição)\s*:\s*(.+)$",
            line,
            re.IGNORECASE,
        )
        if callout:
            flush_paragraph()
            tone = {
                "nota": "note", "dica": "tip", "atenção": "warning",
                "exemplo": "example", "definição": "definition",
            }.get(callout.group(1).casefold(), "note")
            raw.append(("callout", (tone, callout.group(1), callout.group(2))))
            index += 1
            continue
        paragraph.append(line)
        index += 1
    flush_paragraph()

    blocks: list[PedagogicalBlockDTO] = []
    for ordinal, (kind, payload) in enumerate(raw):
        common = {
            "id": _stable_id(document_id, ordinal, kind),
            "ordinal": ordinal,
            "provenance": provenance,
            "license": license_name,
        }
        if kind == "title":
            level, body = payload
            block = TitleBlockDTO(**common, level=level, text=body)
        elif kind == "paragraph":
            block = ParagraphBlockDTO(**common, text=payload)
        elif kind == "list":
            ordered, items = payload
            block = ListBlockDTO(**common, ordered=ordered, items=items)
        elif kind == "code":
            language, code = payload
            block = CodeBlockDTO(**common, language=language, code=code)
        elif kind == "signature":
            block = SignatureBlockDTO(**common, signature=payload)
        elif kind == "formula":
            block = FormulaBlockDTO(**common, latex=payload, spoken=payload)
        elif kind == "table":
            headers, rows = payload
            block = TableBlockDTO(**common, headers=headers, rows=rows)
        elif kind == "callout":
            tone, title, body = payload
            block = CalloutBlockDTO(**common, tone=tone, title=title, body=body)
        else:  # pragma: no cover - raw kinds are exhaustive above
            raise AssertionError(kind)
        blocks.append(block)
    return tuple(blocks)


def build_pedagogical_document(
    *,
    owner_type: PedagogicalOwnerType | str,
    owner_id: str,
    title: str,
    summary: str,
    blocks: Iterable[PedagogicalBlockDTO],
    sources: Iterable[PedagogicalSourceLinkDTO] = (),
    provenance: str = "Aprendix original",
    license_name: str = "MIT",
    locale: str = "pt-PT",
    version: int = 1,
) -> PedagogicalDocumentDTO:
    block_tuple = tuple(blocks)
    source_tuple = tuple(sources)
    document_id = _stable_id(str(owner_type), owner_id, version)
    canonical = {
        "owner_type": owner_type.value if isinstance(owner_type, PedagogicalOwnerType) else owner_type,
        "owner_id": owner_id,
        "title": title,
        "summary": summary,
        "locale": locale,
        "version": version,
        "blocks": [block.model_dump(mode="json") for block in block_tuple],
        "sources": [source.model_dump(mode="json") for source in source_tuple],
        "provenance": provenance,
        "license": license_name,
    }
    now = utc_now()
    return PedagogicalDocumentDTO(
        id=document_id,
        owner_type=owner_type,
        owner_id=owner_id,
        title=normalize_pedagogical_text(title),
        summary=normalize_pedagogical_text(summary),
        locale=locale,
        version=version,
        provenance=provenance,
        license=license_name,
        fingerprint=sha256(_canonical_json(canonical).encode("utf-8")).hexdigest(),
        blocks=block_tuple,
        sources=source_tuple,
        created_at=now,
        updated_at=now,
    )


def deterministic_card_svg(
    *,
    area_title: str,
    fact: str,
    format_name: str,
) -> PedagogicalAssetDTO:
    """Create an original, dependency-free SVG; no external references or script."""

    clean_area = normalize_pedagogical_text(area_title)[:64]
    clean_fact = normalize_pedagogical_text(fact)[:180]
    words = clean_fact.split()
    lines = [" ".join(words[offset:offset + 8]) for offset in range(0, len(words), 8)][:3]
    escaped_area = html.escape(clean_area, quote=True)
    escaped_format = html.escape(format_name.upper(), quote=True)
    text_nodes = "".join(
        f'<text x="320" y="{174 + index * 30}" text-anchor="middle" '
        f'font-family="Arial,sans-serif" font-size="18" fill="#eaf2ff">'
        f'{html.escape(line, quote=True)}</text>'
        for index, line in enumerate(lines)
    )
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" '
        'viewBox="0 0 640 360" role="img">'
        '<rect width="640" height="360" rx="28" fill="#0f172a"/>'
        '<path d="M95 105 H545" stroke="#38bdf8" stroke-width="4"/>'
        '<circle cx="110" cy="105" r="18" fill="#7c3aed"/>'
        '<circle cx="320" cy="105" r="18" fill="#38bdf8"/>'
        '<circle cx="530" cy="105" r="18" fill="#10b981"/>'
        f'<text x="36" y="52" font-family="Arial,sans-serif" font-size="24" '
        f'font-weight="700" fill="#f8fafc">{escaped_area}</text>'
        f'<text x="604" y="50" text-anchor="end" font-family="Arial,sans-serif" '
        f'font-size="13" fill="#94a3b8">{escaped_format}</text>'
        f'{text_nodes}'
        '<text x="320" y="320" text-anchor="middle" font-family="Arial,sans-serif" '
        'font-size="14" fill="#94a3b8">Visual original Aprendix · leitura conceptual</text>'
        '</svg>'
    ).encode()
    digest = sha256(svg).hexdigest()
    alt = f"Diagrama conceptual original sobre {clean_area}: {clean_fact}"
    return PedagogicalAssetDTO(
        id=digest,
        mime_type="image/svg+xml",
        content=svg,
        storage_uri=f"aprendix-asset://{digest}",
        byte_size=len(svg),
        width=640,
        height=360,
        alt_text=alt[:1_000],
        provenance="Gerado deterministicamente pelo Aprendix a partir de conteúdo original.",
        license="MIT",
    )


class PedagogicalDocumentRepositoryProtocol(Protocol):
    def save_document(self, document: PedagogicalDocumentDTO) -> None: ...
    def get_document(self, owner_type: str, owner_id: str) -> PedagogicalDocumentDTO | None: ...
    def save_asset(self, asset: PedagogicalAssetDTO) -> None: ...
    def get_asset(self, asset_id: str) -> PedagogicalAssetDTO | None: ...
    def search_catalog(
        self,
        query: str,
        *,
        entity_types: tuple[str, ...] = (),
        area_ids: tuple[str, ...] = (),
        limit: int = 20,
    ) -> tuple[object, ...]: ...
    def rebuild_catalog_search(self) -> dict[str, int]: ...


class ManagedAssetStore:
    """Materialize verified DB assets into an application-owned cache directory."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def materialize(self, asset: PedagogicalAssetDTO) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        extension = {
            "image/svg+xml": ".svg", "image/png": ".png",
            "image/jpeg": ".jpg", "image/webp": ".webp",
        }[asset.mime_type]
        target = (self.root / f"{asset.id}{extension}").resolve()
        if target.parent != self.root:
            raise ValueError("asset path escaped the managed store")
        if target.exists() and sha256(target.read_bytes()).hexdigest() == asset.id:
            return target
        descriptor, temporary_name = tempfile.mkstemp(prefix="aprendix-", dir=self.root)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(asset.content)
                stream.flush()
                os.fsync(stream.fileno())
            if sha256(Path(temporary_name).read_bytes()).hexdigest() != asset.id:
                raise ValueError("asset hash changed during materialization")
            os.replace(temporary_name, target)
        finally:
            Path(temporary_name).unlink(missing_ok=True)
        return target


class PedagogicalDocumentService:
    def __init__(self, repository: PedagogicalDocumentRepositoryProtocol) -> None:
        self._repository = repository

    def save(self, document: PedagogicalDocumentDTO) -> None:
        self._repository.save_document(document)

    def get(self, owner_type: PedagogicalOwnerType | str, owner_id: str) -> PedagogicalDocumentDTO | None:
        key = owner_type.value if isinstance(owner_type, PedagogicalOwnerType) else owner_type
        return self._repository.get_document(key, owner_id)

    def save_asset(self, asset: PedagogicalAssetDTO) -> None:
        self._repository.save_asset(asset)

    def get_asset(self, asset_id: str) -> PedagogicalAssetDTO | None:
        return self._repository.get_asset(asset_id)

    def search_catalog(
        self,
        query: str,
        *,
        entity_types: tuple[str, ...] = (),
        area_ids: tuple[str, ...] = (),
        limit: int = 20,
    ) -> tuple[object, ...]:
        return self._repository.search_catalog(
            query,
            entity_types=entity_types,
            area_ids=area_ids,
            limit=limit,
        )

    def rebuild_catalog_search(self) -> dict[str, int]:
        """Refresh all rights-safe catalogue entities after a content update."""

        return self._repository.rebuild_catalog_search()
