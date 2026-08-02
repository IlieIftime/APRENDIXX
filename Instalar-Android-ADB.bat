@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

set "APK=%~dp0dist\mobile\Aprendix-0.18.0-android-arm64-debug.apk"
if not exist "%APK%" (
    echo ERRO: APK nao encontrado em:
    echo %APK%
    pause
    exit /b 2
)

set "ADB="
for /f "delims=" %%I in ('where adb.exe 2^>nul') do if not defined ADB set "ADB=%%I"
if not defined ADB set "ADB=%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"
if not exist "%ADB%" (
    echo ERRO: Android Platform Tools/ADB nao foi encontrado.
    echo.
    echo Podes instalar manualmente copiando o APK para o telemovel,
    echo ou instalar o Platform Tools oficial e voltar a executar este BAT.
    pause
    exit /b 3
)

echo Liga o Android por USB, ativa Opcoes de programador e Depuracao USB,
echo e aceita a autorizacao que aparecer no dispositivo.
echo.
"%ADB%" start-server >nul
"%ADB%" get-state 1>nul 2>nul
if errorlevel 1 (
    echo ERRO: nao existe um dispositivo Android autorizado e ligado.
    "%ADB%" devices -l
    pause
    exit /b 4
)

echo A instalar/atualizar o Aprendix...
"%ADB%" install -r "%APK%"
if errorlevel 1 (
    echo.
    echo A instalacao falhou. Se existe uma versao assinada com outra chave,
    echo desinstala-a primeiro; isso tambem elimina os dados locais dessa versao.
    pause
    exit /b 5
)

echo A iniciar o Aprendix...
"%ADB%" shell am start -n io.aprendix.aprendix/org.kivy.android.PythonActivity
if errorlevel 1 (
    echo O APK foi instalado, mas o arranque automatico falhou. Abre o icone Aprendix manualmente.
    pause
    exit /b 6
)

echo.
echo Aprendix instalado e iniciado com sucesso.
pause
exit /b 0
