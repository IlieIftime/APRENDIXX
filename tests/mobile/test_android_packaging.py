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
    toolchain = SimpleNamespace(_dist=SimpleNamespace(dist_dir=str(tmp_path / "dist")))

    module.after_apk_build(toolchain)
    module.after_apk_build(toolchain)

    result = manifest.read_text(encoding="utf-8")
    assert result.count("AprendixReminderReceiver") == 1
    assert result.index("AprendixReminderReceiver") < result.index("</application>")


def test_android_spec_has_no_network_permission_and_uses_manifest_hook() -> None:
    content = (Path(__file__).parents[2] / "buildozer.spec").read_text(encoding="utf-8")
    assert "p4a.hook = mobile/android/p4a_hook.py" in content
    permissions = next(line for line in content.splitlines() if line.startswith("android.permissions"))
    assert "INTERNET" not in permissions
    include_exts = next(line for line in content.splitlines() if line.startswith("source.include_exts"))
    # A pyproject/setup file makes this p4a release archive main.py only and
    # assume the application itself was installed into site-packages.
    assert "toml" not in include_exts
