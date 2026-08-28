param(
    [string]$VenvDirectory = "",
    [string]$InstallDirectory = "",
    [switch]$SkipTests,
    [switch]$RequireMobileRelease,
    [switch]$NoDesktopShortcut,
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path
$versionSource = Join-Path $projectRoot "src\aprendix\__init__.py"

if (-not (Test-Path -LiteralPath $versionSource -PathType Leaf)) {
    throw "Nao foi possivel localizar $versionSource para ler a versao do produto."
}

$versionMatch = [regex]::Match(
    (Get-Content -Raw -LiteralPath $versionSource),
    '__version__\s*=\s*[''\"](?<version>[^''\"]+)[''\"]'
)
if (-not $versionMatch.Success) {
    throw "Nao foi possivel ler __version__ em $versionSource."
}

$productVersion = $versionMatch.Groups["version"].Value

if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    throw "A variavel LOCALAPPDATA nao esta disponivel neste perfil do Windows."
}
if ([string]::IsNullOrWhiteSpace($VenvDirectory)) {
    $VenvDirectory = Join-Path $env:LOCALAPPDATA "AprendixBuild\venv-desktop-$productVersion"
}
elseif (-not [IO.Path]::IsPathRooted($VenvDirectory)) {
    $VenvDirectory = Join-Path $projectRoot $VenvDirectory
}
if ([string]::IsNullOrWhiteSpace($InstallDirectory)) {
    $InstallDirectory = Join-Path $env:LOCALAPPDATA "Programs\Aprendix\$productVersion"
}
elseif (-not [IO.Path]::IsPathRooted($InstallDirectory)) {
    $InstallDirectory = Join-Path $projectRoot $InstallDirectory
}

$venvPath = [IO.Path]::GetFullPath($VenvDirectory)
$installPath = [IO.Path]::GetFullPath($InstallDirectory)
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$builtApplication = Join-Path $projectRoot "dist\Aprendix"
$builtExecutable = Join-Path $builtApplication "Aprendix.exe"
$builtSandbox = Join-Path $projectRoot "dist\AprendixSandbox"
$installedExecutable = Join-Path $installPath "Aprendix.exe"
$installedSandboxExecutable = Join-Path $installPath "AprendixSandbox\AprendixSandbox.exe"

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE)."
    }
}

Write-Output "Aprendix $productVersion - instalacao Windows isolada"
Write-Output "Fontes: $projectRoot"
Write-Output "Venv de construcao: $venvPath"
Write-Output "Aplicacao instalada: $installPath"

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    New-Item -ItemType Directory -Path (Split-Path -Parent $venvPath) -Force | Out-Null
    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($null -ne $launcher) {
        Invoke-Checked -FilePath $launcher.Source `
            -Arguments @("-3", "-m", "venv", $venvPath) `
            -FailureMessage "Nao foi possivel criar a venv com o Python Launcher"
    }
    else {
        $python = Get-Command python -ErrorAction SilentlyContinue
        if ($null -eq $python) {
            throw "Python 3.11 ou superior nao foi encontrado. Instala-o e volta a executar o BAT."
        }
        Invoke-Checked -FilePath $python.Source `
            -Arguments @("-m", "venv", $venvPath) `
            -FailureMessage "Nao foi possivel criar a venv"
    }
}

if (-not (Test-Path -LiteralPath $venvPython -PathType Leaf)) {
    throw "A venv foi criada sem um interpretador Python utilizavel."
}

$pythonVersion = & $venvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($LASTEXITCODE -ne 0) {
    throw "Nao foi possivel verificar a versao de Python da venv."
}
$versionParts = $pythonVersion.Trim().Split(".")
if ([int]$versionParts[0] -lt 3 -or (
    [int]$versionParts[0] -eq 3 -and [int]$versionParts[1] -lt 11
)) {
    throw "O Aprendix requer Python 3.11 ou superior; encontrado $pythonVersion."
}

Push-Location $projectRoot
try {
    Invoke-Checked -FilePath $venvPython `
        -Arguments @("-m", "pip", "install", "--upgrade", "pip>=26.1.2", "setuptools", "wheel") `
        -FailureMessage "Falhou a atualizacao das ferramentas de instalacao"

    Invoke-Checked -FilePath $venvPython `
        -Arguments @("-m", "pip", "install", "-e", ".[gui,rag,cluster-build,desktop-build,dev]") `
        -FailureMessage "Falhou a instalacao das dependencias do Aprendix"

    if (-not $SkipTests) {
        # The mobile Lite database is a generated release input and is ignored
        # by git (*.db). Prepare it before audits that exercise mobile parity.
        Invoke-Checked -FilePath $venvPython `
            -Arguments @("scripts/prepare_mobile_seed.py") `
            -FailureMessage "Nao foi possivel preparar o seed mobile"

        $pytestArguments = @("-m", "pytest", "-q")
        $mobileReleaseApk = Join-Path $projectRoot "dist\mobile\Aprendix-1.0.0-android-arm64-release.apk"
        if (-not (Test-Path -LiteralPath $mobileReleaseApk -PathType Leaf)) {
            if ($RequireMobileRelease) {
                throw "O APK Android release nao foi encontrado em $mobileReleaseApk."
            }
            Write-Warning "APK Android release ausente; o gate de artefacto mobile sera omitido da instalacao Windows."
            $pytestArguments += @("-k", "not test_mobile_install_readme_distinguishes_android_from_ios")
        }
        Invoke-Checked -FilePath $venvPython `
            -Arguments $pytestArguments `
            -FailureMessage "Os testes falharam; a aplicacao nao foi instalada"
    }

    $previousKivyConsoleLog = $env:KIVY_NO_CONSOLELOG
    $previousKivyLogLevel = $env:KCFG_KIVY_LOG_LEVEL
    $previousKivyLogMode = $env:KIVY_LOG_MODE
    $env:KIVY_NO_CONSOLELOG = "1"
    $env:KCFG_KIVY_LOG_LEVEL = "warning"
    $env:KIVY_LOG_MODE = "PYTHON"
    try {
        Invoke-Checked -FilePath $venvPython `
            -Arguments @("-m", "PyInstaller", "--noconfirm", "--clean", "packaging/aprendix.spec") `
            -FailureMessage "O PyInstaller nao conseguiu criar o executavel"
        Invoke-Checked -FilePath $venvPython `
            -Arguments @("-m", "PyInstaller", "--noconfirm", "--clean", "packaging/sandbox.spec") `
            -FailureMessage "O PyInstaller nao conseguiu criar o helper isolado"
    }
    finally {
        if ($null -eq $previousKivyConsoleLog) { Remove-Item Env:KIVY_NO_CONSOLELOG -ErrorAction SilentlyContinue }
        else { $env:KIVY_NO_CONSOLELOG = $previousKivyConsoleLog }
        if ($null -eq $previousKivyLogLevel) { Remove-Item Env:KCFG_KIVY_LOG_LEVEL -ErrorAction SilentlyContinue }
        else { $env:KCFG_KIVY_LOG_LEVEL = $previousKivyLogLevel }
        if ($null -eq $previousKivyLogMode) { Remove-Item Env:KIVY_LOG_MODE -ErrorAction SilentlyContinue }
        else { $env:KIVY_LOG_MODE = $previousKivyLogMode }
    }
}
finally {
    Pop-Location
}

if (-not (Test-Path -LiteralPath $builtExecutable -PathType Leaf)) {
    throw "A compilacao terminou sem criar $builtExecutable."
}
if (-not (Test-Path -LiteralPath (Join-Path $builtSandbox "AprendixSandbox.exe") -PathType Leaf)) {
    throw "A compilacao terminou sem criar o helper de sandbox."
}

New-Item -ItemType Directory -Path $installPath -Force | Out-Null
$installedSandbox = Join-Path $installPath "AprendixSandbox"
New-Item -ItemType Directory -Path $installedSandbox -Force | Out-Null
Copy-Item -Path (Join-Path $builtApplication "*") -Destination $installPath -Recurse -Force
Copy-Item -Path (Join-Path $builtSandbox "*") -Destination $installedSandbox -Recurse -Force
$documentsToInstall = @(
    "LICENSE", "README.md", "docs\guides\INSTALL-MOBILE.md", "docs\architecture\PLANO-MESTRE-AAA-APRENDIX.pdf",
    "docs\releases\RELEASE-NOTES-$productVersion.md", "docs\releases\VALIDATION-$productVersion.md",
    "docs\legacy\iterations\ITERATION-14.md", "docs\legacy\iterations\ITERATION-15.md",
    "docs\legacy\iterations\ITERATION-16.md", "docs\legacy\iterations\ITERATION-17.md",
    "docs\legacy\iterations\ITERATION-19.md", "docs\legacy\iterations\ITERATION-20.md",
    "docs\legacy\iterations\ITERATION-21.md",
    "docs\legacy\iterations\PLAN-ITERATION-20-DESKTOP-LEARNING-WORKSPACE.md",
    "docs\legacy\iterations\PLAN-ITERATION-21-DESKTOP-BOOK-IDE-INTELLIGENCE.md",
    "docs\guides\RECOVERY-GUIDE-1.0.md",
    "docs\architecture\THREAT-MODEL-1.0.md", "reports\SBOM-$productVersion.json",
    "reports\DEPENDENCY-AUDIT-$productVersion.json", "reports\SEARCH-BENCHMARK-$productVersion.json",
    "reports\OCR-BENCHMARK-$productVersion.json", "reports\MULTIMODAL-BENCHMARK-$productVersion.json",
    "reports\SOAK-BENCHMARK-$productVersion.json", "reports\TUTOR-BENCHMARK-AAA.json",
    "reports\BASELINE-$productVersion.json", "reports\AAA-AUDIT-$productVersion.json",
    "reports\ITERATION-13-AUDIT-1.0.0.json", "reports\ITERATION-14-AUDIT-1.0.0.json",
    "reports\ITERATION-15-AUDIT-1.0.0.json", "reports\ITERATION-16-AUDIT-1.0.0.json",
    "reports\ITERATION-17-AUDIT-1.0.0.json", "reports\ITERATION-19-AUDIT-1.0.0.json",
    "reports\ITERATION-20-AUDIT-1.0.0.json", "reports\ITERATION-21-AUDIT-1.0.0.json",
    "reports\ACCESSIBILITY-AUDIT-$productVersion.json", "reports\RELEASE-MANIFEST-$productVersion.json"
)
# Keep future iteration hand-offs (for example 22/23) in the installed
# documentation automatically, without requiring another installer edit.
$iterationDocumentationRoot = Join-Path $projectRoot "docs\legacy\iterations"
$documentsToInstall += Get-ChildItem -LiteralPath $iterationDocumentationRoot -File |
    Where-Object { $_.Name -match '^ITERATION-\d+.*\.(?:md|json)$' } |
    ForEach-Object { Join-Path "docs\legacy\iterations" $_.Name }
$documentsToInstall += Get-ChildItem -LiteralPath $iterationDocumentationRoot -File |
    Where-Object { $_.Name -match '^PLAN-ITERATION-\d+.*\.md$' } |
    ForEach-Object { Join-Path "docs\legacy\iterations" $_.Name }
foreach ($document in ($documentsToInstall | Sort-Object -Unique)) {
    $source = Join-Path $projectRoot $document
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        $destination = Join-Path $installPath $document
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination -Force
    }
}

if (-not (Test-Path -LiteralPath $installedExecutable -PathType Leaf) -or
    -not (Test-Path -LiteralPath $installedSandboxExecutable -PathType Leaf)) {
    throw "A copia para a pasta final de instalacao ficou incompleta."
}

$validationPath = Join-Path $installPath "installation-self-test"
New-Item -ItemType Directory -Path $validationPath -Force | Out-Null
$selfTest = Start-Process -FilePath $installedExecutable `
    -ArgumentList @("--self-test", "--data-dir", ('"' + $validationPath + '"')) `
    -WorkingDirectory $installPath -WindowStyle Hidden -Wait -PassThru
$selfTestReport = Join-Path $validationPath "self-test-report.json"
if ($selfTest.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $selfTestReport -PathType Leaf)) {
    throw "O executavel instalado falhou o self-test (exit code $($selfTest.ExitCode))."
}
$selfTestResult = Get-Content -Raw -LiteralPath $selfTestReport | ConvertFrom-Json
if (-not $selfTestResult.passed) {
    throw "O relatorio do self-test instalado indica falha."
}

$manifest = [ordered]@{
    product = "Aprendix"
    version = $productVersion
    installed_at = (Get-Date).ToUniversalTime().ToString("o")
    executable = $installedExecutable
    executable_sha256 = (Get-FileHash -LiteralPath $installedExecutable -Algorithm SHA256).Hash
    sandbox_sha256 = (Get-FileHash -LiteralPath $installedSandboxExecutable -Algorithm SHA256).Hash
    venv = $venvPath
    python = $pythonVersion.Trim()
    self_test = "passed"
}
$manifest | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $installPath "installation.json") -Encoding UTF8

# The public release manifest must describe the exact executable that has just
# passed the installed self-test, never a previous build copied into the folder.
Invoke-Checked -FilePath $venvPython `
    -Arguments @("scripts/create_release_manifest.py") `
    -FailureMessage "Nao foi possivel criar o manifesto da release instalada"
Invoke-Checked -FilePath $venvPython `
    -Arguments @("scripts/verify_release_manifest.py", "reports\RELEASE-MANIFEST-$productVersion.json") `
    -FailureMessage "O manifesto nao corresponde ao executavel instalado"
$installedReports = Join-Path $installPath "reports"
New-Item -ItemType Directory -Path $installedReports -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $projectRoot "reports\RELEASE-MANIFEST-$productVersion.json") `
    -Destination (Join-Path $installedReports "RELEASE-MANIFEST-$productVersion.json") -Force

if (-not $NoDesktopShortcut) {
    $desktop = [Environment]::GetFolderPath("Desktop")
    if ([string]::IsNullOrWhiteSpace($desktop)) {
        Write-Warning "O Ambiente de Trabalho nao foi localizado; o atalho nao foi criado."
    }
    else {
        $shortcutPath = Join-Path $desktop "Aprendix.lnk"
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        $shortcut.TargetPath = $installedExecutable
        $shortcut.WorkingDirectory = $installPath
        $shortcut.Description = "Abrir o Aprendix"
        $shortcut.Save()
        Write-Output "Atalho criado: $shortcutPath"
    }
}

$sizeMb = [math]::Round((Get-Item -LiteralPath $installedExecutable).Length / 1MB, 1)
Write-Output ""
Write-Output "Instalacao e self-test concluidos."
Write-Output "Executavel: $installedExecutable ($sizeMb MB)"
Write-Output "Venv isolada: $venvPath"

if (-not $NoLaunch) {
    Start-Process -FilePath $installedExecutable -WorkingDirectory $installPath
}
