"""Measure clear-digital OCR character accuracy without retaining images."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path

from aprendix.infrastructure.image_ocr import LocalImageOcr


CASES = (
    "def media(valores):\n    return sum(valores) / len(valores)",
    "for indice, valor in enumerate(dados):\n    print(indice, valor)",
    "SE saldo >= custo ENTAO\n    saldo = saldo - custo\nFIM",
    "class Conta:\n    def depositar(self, valor):\n        self.saldo += valor",
)


def _normal(value: str) -> str:
    return "\n".join(line.rstrip() for line in value.replace("\r\n", "\n").strip().splitlines())


def run(output: Path) -> dict[str, object]:
    from PIL import Image, ImageDraw, ImageFont

    font_candidates = (
        Path("C:/Windows/Fonts/consola.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
    )
    font_path = next((item for item in font_candidates if item.is_file()), None)
    font = ImageFont.truetype(str(font_path), 34) if font_path else ImageFont.load_default()
    scores: list[float] = []
    with tempfile.TemporaryDirectory(prefix="aprendix-ocr-benchmark-") as temporary:
        root = Path(temporary)
        for index, expected in enumerate(CASES):
            image = Image.new("RGB", (1400, 80 + 58 * len(expected.splitlines())), "white")
            ImageDraw.Draw(image).multiline_text((36, 30), expected, fill="black", font=font, spacing=16)
            path = root / f"case-{index}.png"
            image.save(path, "PNG")
            actual = LocalImageOcr().extract(path).text
            scores.append(SequenceMatcher(None, _normal(expected), _normal(actual)).ratio())
    result: dict[str, object] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset": "generated-clear-digital-code-v1",
        "cases": len(CASES),
        "character_accuracy": sum(scores) / len(scores),
        "minimum_case_accuracy": min(scores),
        "target": 0.95,
    }
    result["passed"] = bool(result["character_accuracy"] >= result["target"])
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("reports/OCR-BENCHMARK-1.0.0.json"))
    arguments = parser.parse_args()
    measured = run(arguments.output)
    print(json.dumps(measured, indent=2, ensure_ascii=False))
    raise SystemExit(0 if measured["passed"] else 1)
