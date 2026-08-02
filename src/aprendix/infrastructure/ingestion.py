"""Bounded, resumable local content ingestion with quantized local embeddings."""

from __future__ import annotations

import ast
import hashlib
import json
import math
import re
import unicodedata
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

from aprendix.application.contracts import (
    Complexity,
    ContentKind,
    IngestionSummaryDTO,
)
from aprendix.infrastructure.db import IndexedChunk, IndexedDocument, KnowledgeRepository


DEFAULT_SOURCE_PATHS: tuple[Path, ...] = (
    Path(r"C:\Users\iliei\OneDrive\Ambiente de Trabalho\ebooks e pappers"),
    Path(r"C:\Users\iliei\OneDrive\Ambiente de Trabalho\treino prog\estudo ferias"),
    Path(
        r"C:\Users\iliei\OneDrive\Ambiente de Trabalho\treino prog\estudo ferias"
        r"\exercicios\Algoritmia POO python\Práticas de Python Algoritmia e programação.pdf"
    ),
)

SUPPORTED_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".ipynb", ".py"}
_EXCLUDED_PATH_PARTS = {"bookslazer", "$recycle.bin", ".git", "__pycache__"}
_EXERCISE_RE = re.compile(
    r"(?im)^\s*(?:exerc[ií]cio|problema|enunciado|pr[aá]tica)\s*(?:n[.º°o]?\s*)?(\d+(?:\.\d+)*)?\s*[:.\-]?\s*"
)
_SOLUTION_RE = re.compile(r"(?im)^\s*(?:solu[cç][aã]o|resolu[cç][aã]o)\s*[:.\-]?\s*")
_TOKEN_RE = re.compile(r"[\wÀ-ÿ]+|[^\w\s]", re.UNICODE)


@dataclass(frozen=True, slots=True)
class ExtractedSection:
    text: str
    page_number: int | None
    heading: str
    content_type: ContentKind
    image_path: str | None = None


@dataclass(frozen=True, slots=True)
class ExtractedDocument:
    title: str
    author: str | None
    published_at: date | None
    page_count: int
    sections: tuple[ExtractedSection, ...]


class FeatureHashEmbedding:
    """Offline signed feature hashing, normalized and quantized to int8."""

    model_id = "aprendix-feature-hash-v1-q8"

    def __init__(self, dimensions: int = 384) -> None:
        if dimensions < 64:
            raise ValueError("embedding dimensions must be at least 64")
        self.dimensions = dimensions

    def embed(self, text: str) -> tuple[int, ...]:
        normalized = unicodedata.normalize("NFKC", text).casefold()
        words = re.findall(r"[\wÀ-ÿ]{2,}", normalized)
        features = words + [word[i : i + 3] for word in words for i in range(max(0, len(word) - 2))]
        vector = [0.0] * self.dimensions
        for feature in features[:20_000]:
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "little") % self.dimensions
            sign = 1.0 if digest[4] & 1 else -1.0
            vector[index] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            vector[0] = 1.0
            norm = 1.0
        return tuple(
            max(-127, min(127, round((value / norm) * 100))) for value in vector
        )


class SpecialistPythonBookParser:
    """Separate exercise statements from theory while retaining page provenance."""

    def split(self, text: str, *, page_number: int | None, image_path: str | None = None) -> tuple[ExtractedSection, ...]:
        cleaned = self._clean(text)
        if not cleaned:
            return ()
        matches = list(_EXERCISE_RE.finditer(cleaned))
        if not matches:
            return (
                ExtractedSection(
                    text=cleaned,
                    page_number=page_number,
                    heading=f"Teoria — página {page_number}" if page_number else "Teoria",
                    content_type=ContentKind.THEORY,
                    image_path=image_path,
                ),
            )
        sections: list[ExtractedSection] = []
        if matches[0].start() > 0:
            theory = cleaned[: matches[0].start()].strip()
            if theory:
                sections.append(
                    ExtractedSection(
                        text=theory, page_number=page_number,
                        heading=f"Teoria — página {page_number}" if page_number else "Teoria",
                        content_type=ContentKind.THEORY, image_path=image_path,
                    )
                )
        for index, match in enumerate(matches):
            end = matches[index + 1].start() if index + 1 < len(matches) else len(cleaned)
            statement = cleaned[match.start() : end].strip()
            solution = _SOLUTION_RE.search(statement)
            if solution:
                statement = statement[: solution.start()].strip()
            if len(statement) < 20:
                continue
            number = match.group(1) or str(index + 1)
            sections.append(
                ExtractedSection(
                    text=statement, page_number=page_number,
                    heading=f"Exercício {number}", content_type=ContentKind.EXERCISE,
                    image_path=image_path,
                )
            )
        return tuple(sections)

    @staticmethod
    def _clean(text: str) -> str:
        text = unicodedata.normalize("NFC", text).replace("\x00", "")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{4,}", "\n\n", text)
        return text.strip()[:2_000_000]


class LocalDocumentExtractor:
    def __init__(self) -> None:
        self._specialist = SpecialistPythonBookParser()
        self._ocr = None

    def extract(self, path: Path) -> ExtractedDocument:
        suffix = path.suffix.casefold()
        if suffix == ".pdf":
            return self._extract_pdf(path)
        if suffix in {".jpg", ".jpeg"}:
            return self._extract_image(path)
        if suffix == ".ipynb":
            return self._extract_notebook(path)
        if suffix == ".py":
            return self._extract_python(path)
        raise ValueError(f"unsupported source type: {suffix}")

    def _extract_pdf(self, path: Path) -> ExtractedDocument:
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError('PDF ingestion requires the "rag" extra') from exc
        reader = PdfReader(str(path), strict=False)
        if reader.is_encrypted and not reader.decrypt(""):
            raise ValueError("encrypted PDF cannot be read")
        metadata = reader.metadata or {}
        title = str(metadata.get("/Title") or path.stem).strip()[:500]
        author = str(metadata.get("/Author") or "").strip()[:160] or None
        published = self._pdf_date(metadata.get("/CreationDate"))
        specialist = self._is_specialist(path)
        sections: list[ExtractedSection] = []
        for page_index, page in enumerate(reader.pages, start=1):
            try:
                text = (page.extract_text() or "")[:500_000]
            except Exception as exc:
                text = f""
            if specialist:
                sections.extend(self._specialist.split(text, page_number=page_index))
            elif text.strip():
                sections.append(
                    ExtractedSection(
                        text=self._specialist._clean(text), page_number=page_index,
                        heading=f"Página {page_index}",
                        content_type=self._kind_from_path(path),
                    )
                )
        return ExtractedDocument(
            title=title or path.stem, author=author, published_at=published,
            page_count=len(reader.pages), sections=tuple(sections),
        )

    def _extract_image(self, path: Path) -> ExtractedDocument:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise RuntimeError('image OCR requires the "rag" extra') from exc
        if self._ocr is None:
            self._ocr = RapidOCR(
                det_limit_side_len=960,
                det_limit_type="max",
                intra_op_num_threads=1,
                inter_op_num_threads=1,
            )
        result, _elapsed = self._ocr(str(path), use_cls=False)
        text = "\n".join(
            str(item[1]) for item in (result or ())
            if isinstance(item, (list, tuple)) and len(item) >= 2
        )
        sections = self._specialist.split(
            text, page_number=self._page_number(path), image_path=str(path.resolve())
        )
        return ExtractedDocument(
            title=path.parent.name, author=None, published_at=None,
            page_count=1, sections=sections,
        )

    def _extract_notebook(self, path: Path) -> ExtractedDocument:
        if path.stat().st_size > 50 * 1024 * 1024:
            raise ValueError("notebook exceeds 50 MB parsing limit")
        payload = json.loads(path.read_text(encoding="utf-8"))
        sections: list[ExtractedSection] = []
        for index, cell in enumerate(payload.get("cells", ())):
            if not isinstance(cell, dict) or cell.get("cell_type") not in {"markdown", "code"}:
                continue
            source = cell.get("source", "")
            text = "".join(source) if isinstance(source, list) else str(source)
            text = self._specialist._clean(text)
            if text:
                sections.append(
                    ExtractedSection(
                        text=text, page_number=None, heading=f"Célula {index + 1}",
                        content_type=ContentKind.THEORY,
                    )
                )
        return ExtractedDocument(path.stem, None, None, 0, tuple(sections))

    def _extract_python(self, path: Path) -> ExtractedDocument:
        if path.stat().st_size > 2 * 1024 * 1024:
            raise ValueError("Python source exceeds 2 MB parsing limit")
        text = path.read_text(encoding="utf-8", errors="replace")
        ast.parse(text)
        return ExtractedDocument(
            path.stem, None, None, 0,
            (ExtractedSection(text, None, path.name, ContentKind.THEORY),),
        )

    @staticmethod
    def _pdf_date(raw: object) -> date | None:
        if not raw:
            return None
        match = re.search(r"(19|20)\d{2}(?:0[1-9]|1[0-2])?(?:0[1-9]|[12]\d|3[01])?", str(raw))
        if not match:
            return None
        value = match.group(0)
        try:
            return date(int(value[:4]), int(value[4:6] or "1"), int(value[6:8] or "1"))
        except ValueError:
            return None

    @staticmethod
    def _is_specialist(path: Path) -> bool:
        folded = unicodedata.normalize("NFKD", str(path)).encode("ascii", "ignore").decode().casefold()
        return "algoritmia poo python" in folded or "livr exercicios python" in folded

    @staticmethod
    def _kind_from_path(path: Path) -> ContentKind:
        folded = str(path).casefold()
        if any(word in folded for word in ("paper", "pappers", "artigo", "journal")):
            return ContentKind.PAPER
        if any(word in folded for word in ("exerc", "workout", "prática", "pratica")):
            return ContentKind.EXERCISE
        return ContentKind.THEORY

    @staticmethod
    def _page_number(path: Path) -> int | None:
        matches = re.findall(r"\d+", path.stem)
        return int(matches[-1]) if matches else None


def discover_sources(paths: Sequence[Path]) -> tuple[Path, ...]:
    """Discover supported files without following out-of-root links."""

    discovered: dict[str, Path] = {}
    for raw in paths:
        path = raw.expanduser()
        if not path.exists():
            if path.suffix.casefold() != ".pdf":
                pdf_alias = path.with_suffix(".pdf")
                if pdf_alias.exists():
                    path = pdf_alias
                else:
                    continue
            else:
                continue
        if path.is_file():
            candidates: Iterable[Path] = (path,)
        else:
            candidates = (item for item in path.rglob("*") if item.is_file())
        for candidate in candidates:
            if candidate.is_symlink() or candidate.suffix.casefold() not in SUPPORTED_SUFFIXES:
                continue
            folded_parts = {part.casefold() for part in candidate.parts}
            if folded_parts & _EXCLUDED_PATH_PARTS:
                continue
            resolved = candidate.resolve()
            discovered[unicodedata.normalize("NFC", str(resolved)).casefold()] = resolved
    return tuple(sorted(discovered.values(), key=lambda item: unicodedata.normalize("NFC", str(item)).casefold()))


class ContentIngestionPipeline:
    def __init__(
        self,
        repository: KnowledgeRepository,
        *,
        extractor: LocalDocumentExtractor | None = None,
        embedder: FeatureHashEmbedding | None = None,
        chunk_characters: int = 3_000,
        overlap_characters: int = 300,
    ) -> None:
        if not 500 <= chunk_characters <= 20_000:
            raise ValueError("chunk_characters must be between 500 and 20000")
        if not 0 <= overlap_characters < chunk_characters:
            raise ValueError("overlap must be smaller than chunk size")
        self._repository = repository
        self._extractor = extractor or LocalDocumentExtractor()
        self._embedder = embedder or FeatureHashEmbedding()
        self._chunk_characters = chunk_characters
        self._overlap = overlap_characters

    def ingest(
        self,
        paths: Sequence[Path] = DEFAULT_SOURCE_PATHS,
        *,
        max_files: int | None = None,
        dry_run: bool = False,
        shard_count: int = 1,
        shard_index: int = 0,
        progress: Callable[[int, int, Path], None] | None = None,
    ) -> IngestionSummaryDTO:
        if shard_count < 1 or not 0 <= shard_index < shard_count:
            raise ValueError("invalid ingestion shard")
        started = datetime.now(UTC)
        files = discover_sources(paths)[shard_index::shard_count]
        if max_files is not None:
            files = files[: max(0, max_files)]
        indexed = skipped = failed = chunk_count = card_count = exercise_count = 0
        errors: list[str] = []
        for position, path in enumerate(files, start=1):
            if progress:
                progress(position, len(files), path)
            try:
                content_hash = self._sha256(path)
                if self._repository.contains_hash(content_hash):
                    skipped += 1
                    continue
                extracted = self._extractor.extract(path)
                chunks = self._build_chunks(path, content_hash, extracted)
                if not chunks:
                    skipped += 1
                    continue
                if dry_run:
                    indexed += 1
                    chunk_count += len(chunks)
                    card_count += sum(c.content_type is not ContentKind.EXERCISE for c in chunks)
                    exercise_count += sum(c.content_type is ContentKind.EXERCISE for c in chunks)
                    continue
                stat = path.stat()
                document = IndexedDocument(
                    id=uuid5(NAMESPACE_URL, f"aprendix:document:{content_hash}"),
                    source_path=str(path), content_hash=content_hash,
                    title=extracted.title[:500] or path.stem[:500],
                    author=extracted.author, content_type=self._extractor._kind_from_path(path),
                    complexity=self._complexity(path), published_at=extracted.published_at,
                    page_count=extracted.page_count, file_size=stat.st_size,
                    modified_at=datetime.fromtimestamp(stat.st_mtime, tz=UTC),
                )
                created, cards, exercises = self._repository.store_document(document, chunks)
                if created:
                    indexed += 1
                    chunk_count += len(chunks)
                    card_count += cards
                    exercise_count += exercises
                else:
                    skipped += 1
            except Exception as exc:
                failed += 1
                errors.append(f"{path.name}: {type(exc).__name__}: {str(exc)[:300]}")
        summary = IngestionSummaryDTO(
            started_at=started, completed_at=datetime.now(UTC),
            discovered_files=len(files), indexed_documents=indexed,
            skipped_documents=skipped, failed_documents=failed,
            chunks=chunk_count, theory_cards=card_count, exercises=exercise_count,
            errors=tuple(errors[:100]),
        )
        if not dry_run:
            self._repository.record_run(summary)
        return summary

    def _build_chunks(
        self,
        path: Path,
        content_hash: str,
        extracted: ExtractedDocument,
    ) -> tuple[IndexedChunk, ...]:
        chunks: list[IndexedChunk] = []
        ordinal = 0
        specialist = self._extractor._is_specialist(path)
        for section in extracted.sections:
            for text in self._chunk_text(section.text):
                chunk_id = uuid5(
                    NAMESPACE_URL,
                    f"aprendix:chunk:{content_hash}:{ordinal}:{section.content_type.value}",
                )
                node_slug = None
                if section.content_type is ContentKind.EXERCISE:
                    node_slug = self._slug(section.heading or path.stem, chunk_id)
                chunks.append(
                    IndexedChunk(
                        id=chunk_id, ordinal=ordinal, text=text,
                        content_type=section.content_type,
                        embedding=self._embedder.embed(text), model_id=self._embedder.model_id,
                        page_number=section.page_number, section=section.heading[:500],
                        graph_node_slug=node_slug,
                        image_path=section.image_path,
                    )
                )
                ordinal += 1
        return tuple(chunks)

    def _chunk_text(self, text: str) -> tuple[str, ...]:
        text = text.strip()
        if not text:
            return ()
        chunks: list[str] = []
        start = 0
        while start < len(text):
            end = min(len(text), start + self._chunk_characters)
            if end < len(text):
                boundary = max(text.rfind("\n\n", start, end), text.rfind(". ", start, end))
                if boundary > start + self._chunk_characters // 2:
                    end = boundary + 1
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(text):
                break
            start = max(start + 1, end - self._overlap)
        return tuple(chunks)

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        before = path.stat()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        after = path.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise OSError("source changed while it was being read")
        return digest.hexdigest()

    @staticmethod
    def _complexity(path: Path) -> Complexity:
        folded = str(path).casefold()
        if any(word in folded for word in ("paper", "pappers", "advanced", "deep learning", "cnn", "research")):
            return Complexity.ADVANCED
        if any(word in folded for word in ("poo", "object oriented", "algoritm", "machine learning")):
            return Complexity.INTERMEDIATE
        return Complexity.BEGINNER

    @staticmethod
    def _slug(title: str, chunk_id: UUID) -> str:
        folded = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().casefold()
        base = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")[:55]
        return f"{base or 'conteudo'}-{chunk_id.hex[:8]}"
