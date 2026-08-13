import subprocess
import sys
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from types import SimpleNamespace


def test_p4a_hook_inserts_receiver_once_inside_application(tmp_path: Path) -> None:
    hook_path = Path(__file__).parents[2] / "mobile" / "android" / "p4a_hook.py"
    specification = spec_from_file_location("aprendix_p4a_hook", hook_path)
    assert specification and specification.loader
    module = module_from_spec(specification)
    specification.loader.exec_module(module)
    manifest = tmp_path / "dist" / "src" / "main" / "AndroidManifest.xml"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android">'
        "<application></application></manifest>", encoding="utf-8",
    )
    gradle = tmp_path / "dist" / "build.gradle"
    gradle.write_text("android {\n    defaultConfig {\n    }\n}\n", encoding="utf-8")
    toolchain = SimpleNamespace(_dist=SimpleNamespace(dist_dir=str(tmp_path / "dist")))

    module.after_apk_build(toolchain)
    module.after_apk_build(toolchain)

    result = manifest.read_text(encoding="utf-8")
    assert result.count("AprendixReminderReceiver") == 1
    assert result.index("AprendixReminderReceiver") < result.index("</application>")
    assert 'android.permission.INTERNET" tools:node="remove"' in result
    assert gradle.read_text(encoding="utf-8").count('abiFilters "arm64-v8a"') == 1


def test_android_spec_has_no_network_permission_and_uses_manifest_hook() -> None:
    content = (Path(__file__).parents[2] / "buildozer.spec").read_text(encoding="utf-8")
    assert "p4a.hook = mobile/android/p4a_hook.py" in content
    permissions = next(line for line in content.splitlines() if line.startswith("android.permissions"))
    assert "INTERNET" not in permissions
    include_exts = next(line for line in content.splitlines() if line.startswith("source.include_exts"))
    # A pyproject/setup file makes this p4a release archive main.py only and
    # assume the application itself was installed into site-packages.
    assert "toml" not in include_exts
    requirements = next(line for line in content.splitlines() if line.startswith("requirements"))
    assert "cryptography" not in requirements
    assert "python3==3.11.14" in requirements
    assert "hostpython3==3.11.14" in requirements
    assert "kivy==2.3.1" in requirements
    assert "p4a.branch = v2026.05.09" in content
    assert "p4a.local_recipes = mobile/android/recipes" in content
    assert "android.api = 35" in content
    assert "android.ndk = 28c" in content
    assert "--require-perfect-match" in content

    validator = (Path(__file__).parents[2] / "mobile" / "scripts" / "validate_android.sh").read_text(encoding="utf-8")
    assert "targetSdkVersion:'35'" in validator
    assert "cryptography/" in validator
    assert "OpenSSL 1.1" in validator
    recipe = (Path(__file__).parents[2] / "mobile" / "android" / "recipes" / "kivy" / "__init__.py").read_text(encoding="utf-8")
    assert "Wno-error=incompatible-function-pointer-types" in recipe
    for recipe_name in ("python3", "hostpython3"):
        pin = (Path(__file__).parents[2] / "mobile" / "android" / "recipes" / recipe_name / "__init__.py").read_text(encoding="utf-8")
        assert 'version = "3.11.14"' in pin


def test_android_native_bridge_supports_ide_landscape_and_private_image_capture() -> None:
    root = Path(__file__).parents[2]
    bridge = (root / "mobile" / "android" / "src" / "io" / "aprendix" / "mobile" /
              "AprendixNativeBridge.java").read_text(encoding="utf-8")
    documents = (root / "mobile" / "aprendix_mobile" / "documents.py").read_text(encoding="utf-8")
    app = (root / "mobile" / "aprendix_mobile" / "app.py").read_text(encoding="utf-8")
    assert "SCREEN_ORIENTATION_SENSOR_LANDSCAPE" in bridge
    assert "setEditorLandscape" in bridge and "setEditorLandscape" in app
    assert "ACTION_OPEN_DOCUMENT" in documents and 'setType("image/*")' in documents
    assert "ACTION_IMAGE_CAPTURE" in documents
    assert "_temporary_image.unlink(missing_ok=True)" in app
    for symbol in ('"("', '")"', '"["', '"]"', '"{"', '"}"', '":"', '"_"', '"="', '"⇥"'):
        assert symbol in app


def test_mobile_runtime_import_path_does_not_require_pydantic() -> None:
    root = Path(__file__).parents[2]
    code = (
        "import sys; "
        f"sys.path[:0]=[{str(root / 'src')!r},{str(root / 'mobile')!r}]; "
        "import aprendix_mobile.app, aprendix_mobile.runtime; "
        "from aprendix.application.snippet_analysis import SnippetAnalyzer; "
        "from aprendix_mobile.contracts import SnippetAnalysisDTO,SnippetRequestDTO; "
        "analyzer=SnippetAnalyzer(result_type=SnippetAnalysisDTO); "
        "result=analyzer.analyze(SnippetRequestDTO(text='x = 1')); "
        "loop=analyzer.analyze(SnippetRequestDTO(text='for x in range(3):\\n    print(x)')); "
        "assert result.detected_language == 'python'; "
        "assert result.line_explanations and loop.complexity_time == 'O(n)'; "
        "assert 'pydantic' not in sys.modules"
    )
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-c", code], capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_ios_shell_exposes_core_offline_parity() -> None:
    content = (Path(__file__).parents[2] / "mobile" / "aprendix_mobile" /
               "toga_app.py").read_text(encoding="utf-8")
    for method in (
        "show_glossary", "show_tutor", "show_projects", "open_snippet_image",
        "resume_game", "daily_game", "game_statistics", "export_profile",
        "preview_profile", "import_profile",
    ):
        assert f"def {method}" in content
    assert "runtime.ask_tutor" in content
    assert "runtime.save_project" in content
    assert "runtime.games.save" in content
