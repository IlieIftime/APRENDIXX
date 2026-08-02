[CmdletBinding()]
param(
    [switch]$Yes,
    [switch]$DryRun,
    [switch]$RemoveUserData
)

$ErrorActionPreference = "Stop"
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))

if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    throw "A variavel LOCALAPPDATA nao esta disponivel neste perfil do Windows."
}

$installRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "Programs\Aprendix"))
$buildRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "AprendixBuild"))
$userDataRoot = [IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "Aprendix"))
$legacyVenv = [IO.Path]::GetFullPath((Join-Path $projectRoot ".venv-aprendix-desktop"))
$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = if ([string]::IsNullOrWhiteSpace($desktop)) { $null } else { Join-Path $desktop "Aprendix.lnk" }

function Normalize-Path {
    param([Parameter(Mandatory = $true)][string]$Path)
    return [IO.Path]::GetFullPath($Path).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
}

function Test-ChildPath {
    param(
        [Parameter(Mandatory = $true)][string]$Path,
        [Parameter(Mandatory = $true)][string]$Parent
    )
    $candidate = Normalize-Path $Path
    $root = Normalize-Path $Parent
    return $candidate.StartsWith($root + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)
}

function Add-UniquePath {
    param(
        [Parameter(Mandatory = $true)][AllowEmptyCollection()][Collections.Generic.HashSet[string]]$Set,
        [Parameter(Mandatory = $true)][string]$Path
    )
    [void]$Set.Add((Normalize-Path $Path))
}

$installPaths = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
$venvPaths = New-Object 'Collections.Generic.HashSet[string]' ([StringComparer]::OrdinalIgnoreCase)
$manifestRecords = @()

if (Test-Path -LiteralPath $installRoot -PathType Container) {
    foreach ($versionDirectory in Get-ChildItem -LiteralPath $installRoot -Directory -Force) {
        $manifestPath = Join-Path $versionDirectory.FullName "installation.json"
        if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
            Write-Warning "Ignorada pasta sem installation.json: $($versionDirectory.FullName)"
            continue
        }

        try {
            $manifest = Get-Content -Raw -LiteralPath $manifestPath | ConvertFrom-Json
        }
        catch {
            Write-Warning "Ignorado manifesto invalido: $manifestPath"
            continue
        }

        if ($manifest.product -ne "Aprendix") {
            Write-Warning "Ignorado manifesto de outro produto: $manifestPath"
            continue
        }

        $installPath = Normalize-Path $versionDirectory.FullName
        if (-not (Test-ChildPath -Path $installPath -Parent $installRoot)) {
            throw "Caminho de instalacao recusado pela verificacao de seguranca: $installPath"
        }

        $declaredExecutable = if ($manifest.executable) { Normalize-Path ([string]$manifest.executable) } else { "" }
        if ([string]::IsNullOrWhiteSpace($declaredExecutable) -or
            -not (Test-ChildPath -Path $declaredExecutable -Parent $installPath)) {
            Write-Warning "Ignorado manifesto cujo executavel aponta para fora da instalacao: $manifestPath"
            continue
        }

        Add-UniquePath -Set $installPaths -Path $installPath
        if ($manifest.venv) {
            $declaredVenv = Normalize-Path ([string]$manifest.venv)
            if (Test-ChildPath -Path $declaredVenv -Parent $buildRoot) {
                Add-UniquePath -Set $venvPaths -Path $declaredVenv
            }
            else {
                Write-Warning "Venv recusada por estar fora de AprendixBuild: $declaredVenv"
            }
        }
        $manifestRecords += [ordered]@{
            version = [string]$manifest.version
            manifest = $manifestPath
            install_path = $installPath
            venv = [string]$manifest.venv
        }
    }
}

# Remove tambem venvs de builds Aprendix antigos que ficaram sem instalacao.
if (Test-Path -LiteralPath $buildRoot -PathType Container) {
    foreach ($directory in Get-ChildItem -LiteralPath $buildRoot -Directory -Filter "venv-desktop-*" -Force) {
        if (Test-ChildPath -Path $directory.FullName -Parent $buildRoot) {
            Add-UniquePath -Set $venvPaths -Path $directory.FullName
        }
    }
}

# Esta era a localizacao usada pelo instalador anterior ao manifesto versionado.
if (Test-Path -LiteralPath $legacyVenv -PathType Container) {
    Add-UniquePath -Set $venvPaths -Path $legacyVenv
}

$shortcutApproved = $false
if ($null -ne $shortcutPath -and (Test-Path -LiteralPath $shortcutPath -PathType Leaf)) {
    try {
        $shell = New-Object -ComObject WScript.Shell
        $shortcut = $shell.CreateShortcut($shortcutPath)
        if ($shortcut.TargetPath -and (Test-ChildPath -Path $shortcut.TargetPath -Parent $installRoot)) {
            $shortcutApproved = $true
        }
        else {
            Write-Warning "O atalho Aprendix nao aponta para a pasta oficial e sera preservado."
        }
    }
    catch {
        Write-Warning "Nao foi possivel validar o atalho; sera preservado."
    }
}

Write-Output "Aprendix - desinstalacao Windows"
Write-Output "Manifestos validos encontrados: $($manifestRecords.Count)"
foreach ($path in $installPaths) { Write-Output "Aplicacao: $path" }
foreach ($path in $venvPaths) { Write-Output "Venv: $path" }
if ($shortcutApproved) { Write-Output "Atalho: $shortcutPath" }
if ($RemoveUserData) {
    Write-Output "Dados locais: $userDataRoot (SERAO REMOVIDOS)"
}
else {
    Write-Output "Dados e progresso preservados: $userDataRoot"
}

if ($installPaths.Count -eq 0 -and $venvPaths.Count -eq 0 -and -not $shortcutApproved -and
    (-not $RemoveUserData -or -not (Test-Path -LiteralPath $userDataRoot))) {
    Write-Output "Nao existem componentes instalados para remover."
    exit 0
}

if ($DryRun) {
    Write-Output "Dry-run concluido: nenhum ficheiro foi removido."
    exit 0
}

if (-not $Yes) {
    $answer = Read-Host "Escreve REMOVER para confirmar"
    if ($answer -cne "REMOVER") {
        Write-Output "Desinstalacao cancelada."
        exit 2
    }
}

# Encerra apenas processos cujo executavel esteja dentro da raiz validada.
foreach ($process in Get-Process -Name "Aprendix" -ErrorAction SilentlyContinue) {
    try {
        $processPath = $process.MainModule.FileName
        if ($processPath -and (Test-ChildPath -Path $processPath -Parent $installRoot)) {
            Write-Output "A encerrar Aprendix PID $($process.Id)..."
            Stop-Process -Id $process.Id -Force
            $process.WaitForExit(5000)
        }
    }
    catch {
        Write-Warning "Nao foi possivel verificar ou encerrar o processo PID $($process.Id)."
    }
}

if ($shortcutApproved -and (Test-Path -LiteralPath $shortcutPath -PathType Leaf)) {
    Remove-Item -LiteralPath $shortcutPath -Force
    Write-Output "Atalho removido: $shortcutPath"
}

foreach ($path in ($installPaths | Sort-Object Length -Descending)) {
    if (-not (Test-ChildPath -Path $path -Parent $installRoot)) {
        throw "Remocao recusada pela verificacao de seguranca: $path"
    }
    if (Test-Path -LiteralPath $path -PathType Container) {
        Remove-Item -LiteralPath $path -Recurse -Force
        Write-Output "Instalacao removida: $path"
    }
}

foreach ($path in ($venvPaths | Sort-Object Length -Descending)) {
    $isBuildVenv = Test-ChildPath -Path $path -Parent $buildRoot
    $isLegacyVenv = (Normalize-Path $path) -eq (Normalize-Path $legacyVenv)
    if (-not $isBuildVenv -and -not $isLegacyVenv) {
        throw "Remocao de venv recusada pela verificacao de seguranca: $path"
    }
    if (Test-Path -LiteralPath $path -PathType Container) {
        Remove-Item -LiteralPath $path -Recurse -Force
        Write-Output "Venv removida: $path"
    }
}

if ($RemoveUserData -and (Test-Path -LiteralPath $userDataRoot -PathType Container)) {
    $expectedUserData = Normalize-Path (Join-Path $env:LOCALAPPDATA "Aprendix")
    if ((Normalize-Path $userDataRoot) -ne $expectedUserData) {
        throw "Remocao dos dados recusada pela verificacao de seguranca."
    }
    Remove-Item -LiteralPath $userDataRoot -Recurse -Force
    Write-Output "Dados e progresso removidos: $userDataRoot"
}

foreach ($root in @($installRoot, $buildRoot)) {
    if ((Test-Path -LiteralPath $root -PathType Container) -and
        -not (Get-ChildItem -LiteralPath $root -Force | Select-Object -First 1)) {
        Remove-Item -LiteralPath $root -Force
    }
}

Write-Output "Desinstalacao concluida. Podes agora executar Instalar-Aprendix.bat."
