@echo off
rem Launch Subtitle Translator with a console window (shows log/error messages).
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Subtitle Translator is not installed on this PC yet.
    echo Please double-click setup.bat first, then try again.
    echo.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" app.py %*
pause
