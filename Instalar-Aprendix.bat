@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo Aprendix 0.18.0 - instalacao Windows
echo.
echo Sera criada uma venv isolada em %%LOCALAPPDATA%%\AprendixBuild.
echo A aplicacao final sera instalada em %%LOCALAPPDATA%%\Programs\Aprendix.
echo Nao feche esta janela enquanto os testes e a compilacao decorrem.
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install_windows.ps1" %*
set "INSTALL_EXIT=%ERRORLEVEL%"

if not "%INSTALL_EXIT%"=="0" (
    echo.
    echo A instalacao falhou. Consulta as mensagens acima.
    pause
    exit /b %INSTALL_EXIT%
)

echo.
echo O Aprendix foi validado, instalado e iniciado.
echo Nas proximas utilizacoes, usa o atalho Aprendix no Ambiente de Trabalho.
pause
exit /b 0
