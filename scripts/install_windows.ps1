param(
    [string]$VenvDirectory = "",
    [string]$InstallDirectory = "",
    [switch]$SkipTests,
    [switch]$NoDesktopShortcut,
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"
$productVersion = "1.0.0"
$projectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..")).Path

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
        Invoke-Checked -FilePath $venvPython `
            -Arguments @("-m", "pytest", "-q") `
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
foreach ($document in @("LICENSE", "README.md", "INSTALL-MOBILE.md", "PLANO-MESTRE-AAA-APRENDIX.pdf", "RELEASE-NOTES-1.0.0.md", "VALIDATION-1.0.0.md", "RECOVERY-GUIDE-1.0.md", "THREAT-MODEL-1.0.md", "SBOM-1.0.0.json", "DEPENDENCY-AUDIT-1.0.0.json", "SEARCH-BENCHMARK-1.0.0.json", "OCR-BENCHMARK-1.0.0.json", "MULTIMODAL-BENCHMARK-1.0.0.json", "SOAK-BENCHMARK-1.0.0.json", "TUTOR-BENCHMARK-AAA.json", "BASELINE-1.0.0.json", "AAA-AUDIT-1.0.0.json", "ACCESSIBILITY-AUDIT-1.0.0.json", "RELEASE-MANIFEST-1.0.0.json")) {
    $source = Join-Path $projectRoot $document
    if (Test-Path -LiteralPath $source -PathType Leaf) {
        Copy-Item -LiteralPath $source -Destination (Join-Path $installPath $document) -Force
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
