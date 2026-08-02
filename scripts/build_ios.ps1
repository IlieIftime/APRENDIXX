$ErrorActionPreference = "Stop"

$isMac = [Runtime.InteropServices.RuntimeInformation]::IsOSPlatform(
    [Runtime.InteropServices.OSPlatform]::OSX
)
if (-not $isMac) {
    throw "iOS builds require macOS with Xcode."
}
if (-not (Get-Command briefcase -ErrorAction SilentlyContinue)) {
    throw 'Briefcase is missing. Install with: python -m pip install -e ".[mobile-build]"'
}

python -m pytest -q
if ($LASTEXITCODE -ne 0) {
    throw "Tests failed; iOS package was not built."
}

briefcase create iOS
briefcase build iOS
briefcase package iOS
if ($LASTEXITCODE -ne 0) {
    throw "Briefcase failed."
}

Write-Output "iOS package created under dist/."

