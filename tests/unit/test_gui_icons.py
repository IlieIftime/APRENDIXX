from pathlib import Path

from kivy.graphics.svg import Svg

ROOT = Path(__file__).resolve().parents[2]
ASSET_DIR = ROOT / 'src' / 'aprendix' / 'presentation' / 'assets'


def test_all_gui_icons_parse_without_kivy_svg_errors() -> None:
    for asset in sorted(ASSET_DIR.glob('icon-*.svg')):
        Svg(source=str(asset))
