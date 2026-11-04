@echo off
rem Launch Subtitle Translator without a console window.
rem Video files dropped onto this file are passed to the app.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    rem The Desktop shortcut starts this file minimized, so also show a message box.
    powershell.exe -NoProfile -Command "Add-Type -AssemblyName System.Windows.Forms; [void][System.Windows.Forms.MessageBox]::Show('Subtitle Translator is not installed on this PC yet.' + [char]10 + [char]10 + 'Please double-click setup.bat in the app folder first.', 'Subtitle Translator', 'OK', 'Information')"
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" app.py %*
