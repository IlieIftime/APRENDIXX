"""Render the Aprendix master roadmap Markdown as a styled PDF through Edge."""

from __future__ import annotations

import argparse
import html
import shutil
import subprocess
import tempfile
from pathlib import Path

import markdown


CSS = r"""
@page { size: A4; margin: 18mm 16mm 19mm 16mm; }
* { box-sizing: border-box; }
html { font-size: 10.4pt; }
body {
  margin: 0; color: #152033; background: white;
  font-family: "Segoe UI", Arial, sans-serif; line-height: 1.48;
  -webkit-print-color-adjust: exact; print-color-adjust: exact;
}
.document { max-width: 178mm; margin: 0 auto; }
.cover {
  min-height: 245mm; padding: 36mm 14mm 20mm; border-radius: 7mm;
  color: white; background: linear-gradient(145deg, #0b1220, #172a4f 58%, #6748dc);
  page-break-after: always;
}
.cover h1 { color: white; font-size: 34pt; margin-top: 28mm; border: 0; }
.cover h2 { color: #dce8ff; font-size: 21pt; max-width: 135mm; }
.cover h3 { color: #9fdfff; font-size: 13pt; max-width: 140mm; }
.cover p { color: #e8efff; margin-top: 28mm; }
h1, h2, h3, h4 { color: #10264b; line-height: 1.16; page-break-after: avoid; }
h1 { font-size: 23pt; margin: 11mm 0 5mm; padding-bottom: 2.5mm; border-bottom: 2px solid #6d50e6; }
h2 { font-size: 16pt; margin: 8mm 0 3mm; }
h3 { font-size: 12.5pt; margin: 6mm 0 2mm; color: #31527f; }
p { margin: 0 0 3.1mm; orphans: 3; widows: 3; }
ul, ol { margin: 2mm 0 4mm 6mm; padding-left: 5mm; }
li { margin: 1.1mm 0; }
blockquote {
  margin: 5mm 0; padding: 4mm 5mm; border-left: 4px solid #7254e8;
  background: #f1efff; color: #253452; border-radius: 0 3mm 3mm 0;
}
code { font-family: "Cascadia Mono", Consolas, monospace; background: #eef2f7; padding: .3mm 1mm; border-radius: 1mm; }
pre { white-space: pre-wrap; background: #101827; color: #edf5ff; padding: 4mm; border-radius: 2mm; page-break-inside: avoid; }
pre code { color: inherit; background: transparent; padding: 0; }
table { width: 100%; border-collapse: collapse; margin: 4mm 0 6mm; font-size: 9.1pt; page-break-inside: auto; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
th { background: #1b3156; color: white; text-align: left; font-weight: 650; }
th, td { border: 1px solid #cbd5e4; padding: 2.2mm 2.4mm; vertical-align: top; }
tbody tr:nth-child(even) { background: #f5f7fb; }
a { color: #4e37be; text-decoration: none; }
hr { border: 0; border-top: 1px solid #cbd5e4; margin: 7mm 0; }
.toc { padding: 5mm 7mm; background: #f5f7fb; border: 1px solid #d9e0eb; border-radius: 3mm; }
.toc ul { list-style: none; margin: 1mm 0; padding-left: 4mm; }
.toc a { color: #243b60; }
.page-break { page-break-before: always; height: 0; }
@media print {
  .document { max-width: none; }
  h1 { page-break-before: auto; }
}
"""


def edge_path() -> Path:
    candidates = (
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    executable = shutil.which("msedge")
    if executable:
        return Path(executable)
    raise FileNotFoundError("Microsoft Edge não foi encontrado para gerar o PDF.")


def render(source: Path, output: Path) -> None:
    source = source.resolve()
    output = output.resolve()
    body = markdown.markdown(
        source.read_text(encoding="utf-8"),
        extensions=("extra", "toc", "sane_lists", "smarty"),
        extension_configs={"toc": {"permalink": False}},
    )
    title = "Aprendix AAA — Plano mestre de produto e implementação"
    document = f"""<!doctype html>
<html lang="pt-PT"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>{CSS}</style></head>
<body><main class="document">{body}</main></body></html>"""
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="aprendix-roadmap-") as temporary:
        temporary_path = Path(temporary)
        html_path = temporary_path / "roadmap.html"
        profile_path = temporary_path / "edge-profile"
        html_path.write_text(document, encoding="utf-8")
        command = [
            str(edge_path()), "--headless", "--disable-gpu", "--no-pdf-header-footer",
            f"--user-data-dir={profile_path}", f"--print-to-pdf={output}",
            html_path.as_uri(),
        ]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if completed.returncode != 0 or not output.is_file() or output.stat().st_size < 10_000:
            raise RuntimeError(
                "Falha ao gerar PDF. "
                f"exit={completed.returncode}; stdout={completed.stdout}; stderr={completed.stderr}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    render(args.source, args.output)
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
