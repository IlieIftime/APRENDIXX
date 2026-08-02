@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo Aprendix - desinstalacao Windows
echo.
echo Este processo le os manifestos installation.json antes de remover:
echo - instalacoes Aprendix versionadas;
echo - venvs Aprendix antigas e atuais;
echo - o atalho validado do Ambiente de Trabalho.
echo.
echo A base de dados e o progresso local sao preservados por defeito.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\uninstall_windows.ps1" %*
set "UNINSTALL_EXIT=%ERRORLEVEL%"

if "%UNINSTALL_EXIT%"=="0" (
    echo.
    echo Operacao terminada. Podes agora executar Instalar-Aprendix.bat.
) else if "%UNINSTALL_EXIT%"=="2" (
    echo.
    echo Operacao cancelada pelo utilizador.
) else (
    echo.
    echo A desinstalacao falhou. Consulta as mensagens acima.
)

pause
exit /b %UNINSTALL_EXIT%
