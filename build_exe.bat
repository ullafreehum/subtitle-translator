@echo off
rem Build a standalone Subtitle Translator (no Python needed on the target PC).
rem Result: dist\SubtitleTranslator\  (about 2.2 GB, ~1150 files) - copy or zip the whole folder.
rem It holds SubtitleTranslator.exe (the app) and SubtitleTranslatorCLI.exe (command line).
rem Models are not included: the NLLB translation model downloads into
rem dist\SubtitleTranslator\models, the Whisper speech model into the user's
rem %USERPROFILE%\.cache\huggingface folder, on first use.
rem A rebuild keeps dist\SubtitleTranslator\models, glossary.txt and settings.json.
rem The target PC still needs ffmpeg/ffprobe/ffplay (winget install Gyan.FFmpeg),
rem or copy ffmpeg.exe, ffprobe.exe and ffplay.exe next to SubtitleTranslator.exe.
setlocal
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
set "OUT=dist\SubtitleTranslator"
set "KEEP=dist\_keep"

if not exist "%PY%" (
    echo .venv not found. Run setup.bat first.
    goto :fail
)
for %%M in (app editor engine translation subtitles glossary) do (
    if not exist "%%M.py" (
        echo Missing %%M.py - cannot build.
        goto :fail
    )
)

"%PY%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller into .venv ...
    "%PY%" -m pip install --disable-pip-version-check pyinstaller
    if errorlevel 1 goto :fail
)

rem PyInstaller empties dist\SubtitleTranslator: move downloaded models and user files aside.
if exist "%OUT%" (
    if not exist "%KEEP%" mkdir "%KEEP%"
    for %%F in (models glossary.txt settings.json) do (
        if exist "%OUT%\%%F" move "%OUT%\%%F" "%KEEP%\" >nul || (
            echo Could not move %OUT%\%%F - close Subtitle Translator and try again.
            goto :restore_fail
        )
    )
)

echo Building ... this takes 5-15 minutes and copies about 2 GB of CUDA libraries.
"%PY%" -m PyInstaller --noconfirm --clean SubtitleTranslator.spec
if errorlevel 1 goto :restore_fail
call :restore
rem build\ only holds PyInstaller's working files; its half-made exe cannot run, so remove it.
if exist "build" rmdir /s /q "build"

echo.
echo Done: "%~dp0%OUT%\SubtitleTranslator.exe"
echo Command line version: "%~dp0%OUT%\SubtitleTranslatorCLI.exe"
if not defined BUILD_NOPAUSE pause
exit /b 0

:restore
if not exist "%KEEP%" exit /b 0
if not exist "%OUT%" mkdir "%OUT%"
for %%F in (models glossary.txt settings.json) do (
    if exist "%KEEP%\%%F" move "%KEEP%\%%F" "%OUT%\" >nul
)
rmdir "%KEEP%" 2>nul
exit /b 0

:restore_fail
call :restore
:fail
echo.
echo Build failed - see the messages above.
if not defined BUILD_NOPAUSE pause
exit /b 1
