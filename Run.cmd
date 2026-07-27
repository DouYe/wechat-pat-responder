@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0WeChatPatResponder.exe" (
    start "" "%~dp0WeChatPatResponder.exe"
    exit /b 0
)

if exist "%~dp0.venv\Scripts\pythonw.exe" (
    start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0WeChatPatResponder.py"
    exit /b 0
)

echo The application has not been set up.
echo Run Setup.cmd first.
pause
exit /b 1
