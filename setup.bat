@echo off
rem Install Subtitle Translator on this PC: double-click this file.
rem Safe to run again (it only adds what is missing). Options are passed to setup.ps1,
rem e.g.  setup.bat -SkipShortcuts     or     setup.bat -DryRun
rem Set SETUP_NOPAUSE=1 to never wait for a key press (automated runs).
setlocal
cd /d "%~dp0"
title Subtitle Translator - Setup
if not exist "%~dp0setup.ps1" goto :notextracted
if not exist "%~dp0requirements.txt" goto :notextracted
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup.ps1" %*
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" goto :end
if "%RC%"=="2" (
    echo Please close this window and double-click setup.bat once more.
) else if "%RC%"=="3" (
    echo Setup finished, but please read the warnings above.
) else (
    echo Setup did not finish. Read the red message above, fix it, and run setup.bat again.
)
goto :end

:notextracted
echo The Subtitle Translator files are not complete in this folder:
echo   "%~dp0"
echo.
echo If you downloaded a ZIP file: right-click the ZIP, choose "Extract All...",
echo open the extracted folder and double-click setup.bat there.
echo (Starting setup.bat directly from inside the ZIP does not work.)
set "RC=1"

:end
if not defined SETUP_NOPAUSE pause
exit /b %RC%
