"""Exercise OCR formats, degraded inputs and malformed-image fail-closed paths."""

from __future__ import annotations

import argparse
import json
import random
import tempfile
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path

from aprendix.infrastructure.image_ocr import LocalImageOcr


EXPECTED = "def limite(valor):\n    return max(0, min(valor, 100))"


def _normal(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.replace("\r\n", "\n").strip().splitlines())


def run(output: Path) -> dict[str, object]:
    from PIL import Image, ImageDraw, ImageEnhance, ImageFont

    font_candidates = (
        Path("C:/Windows/Fonts/consola.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    )
    font_path = next((item for item in font_candidates if item.is_file()), None)
    font = ImageFont.truetype(str(font_path), 34) if font_path else ImageFont.load_default()
    scores: dict[str, float] = {}
    confirmation = True
    rejected = 0
    with tempfile.TemporaryDirectory(prefix="aprendix-multimodal-") as temporary:
        root = Path(temporary)
        base = Image.new("RGB", (1250, 205), "white")
        ImageDraw.Draw(base).multiline_text((35, 28), EXPECTED, fill="black", font=font, spacing=18)
        variants = {
            "png_clear": (base, "PNG", {}),
            "jpeg_compressed": (base, "JPEG", {"quality": 45}),
            "webp_lossless": (base, "WEBP", {"lossless": True}),
            "rotated_1_5deg": (base.rotate(1.5, expand=True, fillcolor="white"), "PNG", {}),
            "low_contrast": (ImageEnhance.Contrast(base).enhance(0.45), "PNG", {}),
        }
        ocr = LocalImageOcr()
        for name, (image, image_format, options) in variants.items():
            path = root / f"{name}.{image_format.casefold()}"
            image.save(path, image_format, **options)
            draft = ocr.extract(path)
            scores[name] = SequenceMatcher(None, _normal(EXPECTED), _normal(draft.text)).ratio()
            confirmation = confirmation and draft.requires_confirmation
        randomizer = random.Random(917)
        for index in range(64):
            malformed = root / f"malformed-{index}.png"
            malformed.write_bytes(randomizer.randbytes(randomizer.randint(0, 8192)))
            try:
                ocr.extract(malformed)
            except (ValueError, RuntimeError, OSError):
                rejected += 1
    report: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": "generated-multiformat-and-degraded-code-v1",
        "format_cases": scores,
        "clear_accuracy_target": 0.95,
        "clear_accuracy_passed": scores["png_clear"] >= 0.95,
        "all_require_confirmation": confirmation,
        "malformed_cases": 64,
        "malformed_rejected": rejected,
    }
    report["passed"] = bool(
        report["clear_accuracy_passed"]
        and confirmation
        and rejected == report["malformed_cases"]
        and len(scores) == 5
    )
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("reports/MULTIMODAL-BENCHMARK-1.0.0.json"))
    arguments = parser.parse_args()
    measured = run(arguments.output.resolve())
    print(json.dumps(measured, indent=2, ensure_ascii=False))
    raise SystemExit(0 if measured["passed"] else 1)
