@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\Update-And-Run.ps1"
set "updateExitCode=%errorlevel%"

if not "%updateExitCode%"=="0" (
    echo.
    echo Update failed. The previous installation was preserved.
    pause
)

exit /b %updateExitCode%
