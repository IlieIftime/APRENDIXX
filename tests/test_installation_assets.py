import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_windows_installer_separates_build_venv_and_installed_application() -> None:
    script = (ROOT / "scripts" / "install_windows.ps1").read_text(encoding="utf-8")
    assert '"AprendixBuild\\venv-desktop-$productVersion"' in script
    assert '"Programs\\Aprendix\\$productVersion"' in script
    assert "installation-self-test" in script
    assert 'self_test = "passed"' in script
    assert "$shortcut.TargetPath = $installedExecutable" in script
    for iteration in range(15, 18):
        assert f'"ITERATION-{iteration}.md"' in script
        assert f'"ITERATION-{iteration}-AUDIT-1.0.0.json"' in script
    assert '"ITERATION-19.md"' in script
    assert '"ITERATION-19-AUDIT-1.0.0.json"' in script
    assert '"ITERATION-20.md"' in script
    assert '"ITERATION-20-AUDIT-1.0.0.json"' in script
    assert '"ITERATION-21.md"' in script
    assert '"ITERATION-21-AUDIT-1.0.0.json"' in script


def test_release_scan_only_allows_dynamic_execution_in_child_boundaries() -> None:
    script = (ROOT / "scripts" / "verify_release.ps1").read_text(encoding="utf-8")
    for boundary in ("python_sandbox.py", "grading.py", "debugger.py"):
        assert f'-g "!**/{boundary}"' in script


def test_clickable_installers_reference_valid_artifacts_and_launchers() -> None:
    windows = (ROOT / "Instalar-Aprendix.bat").read_text(encoding="utf-8")
    android = (ROOT / "Instalar-Android-ADB.bat").read_text(encoding="utf-8")
    assert "scripts\\install_windows.ps1" in windows
    assert "Aprendix-1.0.0-android-arm64-release.apk" in android
    assert 'install -r "%APK%"' in android
    assert "io.aprendix.aprendix/org.kivy.android.PythonActivity" in android


def test_windows_uninstaller_has_manifest_and_path_safety_guards() -> None:
    wrapper = (ROOT / "Desinstalar-Aprendix.bat").read_text(encoding="utf-8")
    script = (ROOT / "scripts" / "uninstall_windows.ps1").read_text(encoding="utf-8")
    assert "scripts\\uninstall_windows.ps1" in wrapper
    assert 'Join-Path $versionDirectory.FullName "installation.json"' in script
    assert '$manifest.product -ne "Aprendix"' in script
    assert "Test-ChildPath" in script
    assert 'Join-Path $projectRoot ".venv-aprendix-desktop"' in script
    assert 'Directory -Filter "venv-desktop-*"' in script
    assert "if ($RemoveUserData" in script
    assert "if ($DryRun)" in script


def test_windows_uninstaller_dry_run_and_isolated_removal(tmp_path: Path) -> None:
    powershell = shutil.which("powershell.exe")
    if powershell is None:
        return

    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    copied_script = scripts / "uninstall_windows.ps1"
    shutil.copy2(ROOT / "scripts" / "uninstall_windows.ps1", copied_script)

    local = tmp_path / "local"
    install = local / "Programs" / "Aprendix" / "0.1.0"
    venv = local / "AprendixBuild" / "venv-desktop-0.1.0"
    legacy = project / ".venv-aprendix-desktop"
    user_data = local / "Aprendix"
    for directory in (install, venv, legacy, user_data):
        directory.mkdir(parents=True)
        (directory / "sentinel.txt").write_text("keep-check", encoding="utf-8")
    executable = install / "Aprendix.exe"
    executable.write_bytes(b"test")
    (install / "installation.json").write_text(
        json.dumps(
            {
                "product": "Aprendix",
                "version": "0.1.0",
                "executable": str(executable),
                "venv": str(venv),
            }
        ),
        encoding="utf-8",
    )

    environment = os.environ.copy()
    environment["LOCALAPPDATA"] = str(local)
    command = [
        powershell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(copied_script),
        "-Yes",
    ]
    dry_run = subprocess.run(
        [*command, "-DryRun"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert dry_run.returncode == 0, dry_run.stderr
    assert install.exists() and venv.exists() and legacy.exists() and user_data.exists()

    removal = subprocess.run(
        command,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert removal.returncode == 0, removal.stderr
    assert not install.exists()
    assert not venv.exists()
    assert not legacy.exists()
    assert user_data.exists()


def test_mobile_install_readme_distinguishes_android_from_ios() -> None:
    guide = (ROOT / "INSTALL-MOBILE.md").read_text(encoding="utf-8")
    apk = ROOT / "dist" / "mobile" / "Aprendix-1.0.0-android-arm64-release.apk"
    with apk.open("rb") as artifact:
        apk_sha256 = hashlib.file_digest(artifact, "sha256").hexdigest().upper()
    assert apk_sha256 in guide
    assert "Instalar-Android-ADB.bat" in guide
    assert "build_ios.sh" in guide
    assert "não pode ser instalado num iPhone" in guide
    assert "Product > Archive" in guide


def test_ios_script_stops_at_xcode_project_instead_of_fake_installer() -> None:
    script = (ROOT / "mobile" / "scripts" / "build_ios.sh").read_text(encoding="utf-8")
    assert "briefcase build iOS" in script
    assert "integrate_ios_bridge.rb" in script
    assert "briefcase package iOS" not in script
