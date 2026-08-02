$ErrorActionPreference = "Stop"

if ($IsWindows -or $env:OS -eq "Windows_NT") {
    throw "Android builds require Linux/macOS. Run this script inside WSL2 or CI."
}
if (-not (Get-Command buildozer -ErrorAction SilentlyContinue)) {
    throw 'Buildozer is missing. Install with: python -m pip install -e ".[mobile-build]"'
}

python -m pytest -q
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed; Android package was not built."
}

buildozer android debug
if ($LASTEXITCODE -ne 0) {
    throw "Buildozer failed."
}

Write-Output "Android debug artifact created under bin/."

