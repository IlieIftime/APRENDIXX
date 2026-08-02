$ErrorActionPreference = "Stop"

if (-not (Get-Command pyinstaller -ErrorAction SilentlyContinue)) {
    throw 'PyInstaller is missing. Install with: python -m pip install -e ".[desktop-build,gui,rag]"'
}

python -m pytest -q
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed; desktop package was not built."
}

$previousKivyLogMode = $env:KIVY_LOG_MODE
$env:KIVY_LOG_MODE = "PYTHON"
try {
    pyinstaller --noconfirm --clean packaging/aprendix.spec
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed."
    }
    pyinstaller --noconfirm --clean packaging/sandbox.spec
    if ($LASTEXITCODE -ne 0) {
        throw "Sandbox helper build failed."
    }
}
finally {
    if ($null -eq $previousKivyLogMode) {
        Remove-Item Env:KIVY_LOG_MODE -ErrorAction SilentlyContinue
    }
    else {
        $env:KIVY_LOG_MODE = $previousKivyLogMode
    }
}

Write-Output "Desktop artifact created at dist/Aprendix.exe."
