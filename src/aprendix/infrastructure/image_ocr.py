"""Bounded local OCR adapter; image text is untrusted and always confirmed."""

from __future__ import annotations

import struct
import tempfile
import re
from statistics import median
from pathlib import Path

from aprendix.application.contracts import OcrDraftDTO, OcrRegionDTO


class LocalImageOcr:
    MAX_BYTES = 20 * 1024 * 1024
    MAX_PIXELS = 25_000_000

    def extract(self, path: Path) -> OcrDraftDTO:
        path = path.expanduser().resolve()
        if not path.is_file() or path.stat().st_size > self.MAX_BYTES:
            raise ValueError("Imagem inexistente ou superior a 20 MB.")
        data = path.read_bytes()
        kind, width, height = self._identify(data)
        if width <= 0 or height <= 0 or width * height > self.MAX_PIXELS:
            raise ValueError("Dimensões de imagem inválidas ou superiores a 25 MP.")
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as exc:
            raise RuntimeError("OCR local indisponível; instala o extra `rag` do Aprendix.") from exc
        clean_path = path
        temporary_name = None
        try:
            try:
                from PIL import Image, ImageEnhance, ImageFilter, ImageOps
                with Image.open(path) as image:
                    image = ImageOps.exif_transpose(image).convert("RGB")
                    # A conservative local preprocessing pass improves small
                    # code glyphs without inventing strokes. EXIF data is not
                    # copied to the temporary PNG.
                    image = ImageOps.autocontrast(image, cutoff=1)
                    image = image.filter(ImageFilter.MedianFilter(size=3))
                    image = ImageEnhance.Contrast(image).enhance(1.25)
                    image = image.filter(ImageFilter.UnsharpMask(radius=1, percent=125, threshold=3))
                    handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                    temporary_name = handle.name; handle.close()
                    image.save(temporary_name, "PNG", optimize=True)
                    clean_path = Path(temporary_name)
            except ImportError:
                pass
            result, _elapsed = RapidOCR()(str(clean_path), use_cls=True)
        finally:
            if temporary_name:
                Path(temporary_name).unlink(missing_ok=True)
        regions = []
        for item in result or ():
            box, text, confidence = item
            confidence = float(confidence)
            ambiguous = confidence < .85 or bool(set(str(text)) & set("OlI1:;"))
            regions.append(OcrRegionDTO(
                text=str(text), confidence=confidence,
                box=tuple((int(point[0]), int(point[1])) for point in box),
                ambiguous=ambiguous,
            ))
        combined = self._combine_regions(regions)
        confidence = sum(item.confidence for item in regions) / len(regions) if regions else 0.0
        warnings = [f"Formato {kind}, {width}×{height}; metadata removida no processamento."]
        if any(item.ambiguous for item in regions):
            warnings.append("Confirma caracteres ambíguos como 0/O, 1/l, dois-pontos e indentação.")
        if not regions: warnings.append("Não foi detetado texto legível.")
        return OcrDraftDTO(
            text=combined, confidence=confidence, regions=tuple(regions),
            warnings=tuple(warnings), requires_confirmation=True,
        )

    @staticmethod
    def _combine_regions(regions: list[OcrRegionDTO]) -> str:
        """Reconstruct logical code lines from OCR word/fragment boxes."""
        positioned = []
        for region in regions:
            if not region.box:
                continue
            xs = [point[0] for point in region.box]
            ys = [point[1] for point in region.box]
            positioned.append({
                "region": region,
                "x0": min(xs), "x1": max(xs),
                "yc": (min(ys) + max(ys)) / 2,
                "height": max(1, max(ys) - min(ys)),
            })
        if not positioned:
            return "\n".join(item.text for item in regions)
        lines: list[list[dict[str, object]]] = []
        for item in sorted(positioned, key=lambda value: (float(value["yc"]), int(value["x0"]))):
            if not lines:
                lines.append([item]); continue
            current = lines[-1]
            centre = median(float(value["yc"]) for value in current)
            height = median(float(value["height"]) for value in current)
            if abs(float(item["yc"]) - centre) <= max(height, float(item["height"])) * .65:
                current.append(item)
            else:
                lines.append([item])
        left_edge = min(int(item["x0"]) for item in positioned)
        widths = [
            max(1, int(item["x1"]) - int(item["x0"])) / max(1, len(item["region"].text))
            for item in positioned if item["region"].text.strip()
        ]
        character_width = max(1.0, median(widths)) if widths else 8.0
        result = []
        for line in lines:
            ordered = sorted(line, key=lambda value: int(value["x0"]))
            indent_columns = round((int(ordered[0]["x0"]) - left_edge) / character_width)
            indent = " " * (4 * max(0, round(indent_columns / 4)))
            body = " ".join(item["region"].text.strip() for item in ordered)
            body = re.sub(r"\s+([,;:\)\]\}])", r"\1", body)
            body = re.sub(r"([\(\[\{])\s+", r"\1", body)
            result.append(indent + body)
        return "\n".join(result)

    @staticmethod
    def _identify(data: bytes) -> tuple[str, int, int]:
        if len(data) >= 24 and data.startswith(b"\x89PNG\r\n\x1a\n"):
            return "PNG", *struct.unpack(">II", data[16:24])
        if len(data) >= 30 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
            variant = data[12:16]
            if variant == b"VP8X":
                width = 1 + int.from_bytes(data[24:27], "little")
                height = 1 + int.from_bytes(data[27:30], "little")
                return "WebP", width, height
            if variant == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
                width = int.from_bytes(data[26:28], "little") & 0x3FFF
                height = int.from_bytes(data[28:30], "little") & 0x3FFF
                return "WebP", width, height
            if variant == b"VP8L" and data[20] == 0x2F:
                bits = int.from_bytes(data[21:25], "little")
                width = 1 + (bits & 0x3FFF)
                height = 1 + ((bits >> 14) & 0x3FFF)
                return "WebP", width, height
        if data.startswith(b"\xff\xd8"):
            offset = 2
            while offset + 9 < len(data):
                if data[offset] != 0xFF: offset += 1; continue
                marker = data[offset + 1]; offset += 2
                if marker in {0xD8, 0xD9}: continue
                if offset + 2 > len(data): break
                length = int.from_bytes(data[offset:offset+2], "big")
                if marker in {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}:
                    if offset + 7 > len(data): break
                    height = int.from_bytes(data[offset+3:offset+5], "big")
                    width = int.from_bytes(data[offset+5:offset+7], "big")
                    return "JPEG", width, height
                if length < 2: break
                offset += length
        raise ValueError("Apenas PNG, JPEG e WebP válidos são aceites.")
