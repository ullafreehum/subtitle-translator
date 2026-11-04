<#
.SYNOPSIS
    Installs Subtitle Translator on this Windows PC (run it through setup.bat).

.DESCRIPTION
    Safe to run again at any time: every step first checks what is already there.
      1. Python 3.12            (installed with winget if missing)
      2. ffmpeg/ffprobe/ffplay  (installed with winget if missing)
      3. .venv with Python 3.12 + packages from requirements.txt
      4. Check that the packages load (and whether an NVIDIA GPU can be used)
      5. "Subtitle Translator" shortcuts on the Desktop and in the Start menu

.PARAMETER SkipShortcuts
    Do not create the Desktop / Start-menu shortcuts.

.PARAMETER DryRun
    Only show what would be done (alias: -WhatIf). Nothing is installed or changed;
    checks that only read (versions, imports, "pip install --dry-run") still run.

.PARAMETER AssumeMissing
    Testing aid, only together with -DryRun: pretend python, ffmpeg and/or venv are
    missing so the install branches can be checked without touching this PC.

.EXAMPLE
    setup.bat
    setup.bat -SkipShortcuts
    powershell -ExecutionPolicy Bypass -File setup.ps1 -DryRun -AssumeMissing python,ffmpeg,venv
#>
param(
    [switch]$SkipShortcuts,
    [Alias('WhatIf')][switch]$DryRun,
    [string[]]$AssumeMissing = @()
)

# 'powershell -File' passes 'a,b' as one string: split it here.
$AssumeMissing = @($AssumeMissing | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim().ToLowerInvariant() } | Where-Object { $_ })

# Native tools (pip, winget) write progress to stderr; with 'Stop' Windows PowerShell 5.1
# would treat that as a failure. Errors are checked explicitly via $LASTEXITCODE instead.
$ErrorActionPreference = 'Continue'
Set-StrictMode -Version 2

$AppName  = 'Subtitle Translator'
$AppDir   = $PSScriptRoot
$VenvDir  = Join-Path $AppDir '.venv'
$VenvPy   = Join-Path $VenvDir 'Scripts\python.exe'
$Reqs     = Join-Path $AppDir 'requirements.txt'
$RunBat   = Join-Path $AppDir 'run.bat'
$IconFile = Join-Path $AppDir 'assets\icon.ico'
$Steps    = 5
# Longer network timeout for slow connections (pip's default is 15 s); pip resumes
# interrupted downloads by itself, and a re-run reuses the already downloaded files.
$PipOpts  = @('--disable-pip-version-check', '--timeout', '60', '--retries', '10')
# Python/pip print the folder path; with output redirected (log file, remote tools) they would
# use the ANSI code page and pip crashes on Turkish letters (dotless i, ...) in the folder name.
$env:PYTHONIOENCODING = 'utf-8'
$script:Warnings = New-Object System.Collections.Generic.List[string]

class SetupStop : System.Exception {
    [int]$Code
    SetupStop([string]$msg, [int]$code) : base($msg) { $this.Code = $code }
}

# ------------------------------------------------------------------ output helpers
function Write-Step([int]$n, [string]$msg) {
    Write-Host ''
    Write-Host "[$n/$Steps] $msg" -ForegroundColor Cyan
}
function Write-Ok([string]$msg)   { Write-Host "  OK    $msg" -ForegroundColor Green }
function Write-Info([string]$msg) { Write-Host "        $msg" }
function Write-Dry([string]$msg)  { Write-Host "  DRY   would $msg" -ForegroundColor Magenta }
function Add-Warning([string]$msg) {
    Write-Host "  WARN  $msg" -ForegroundColor Yellow
    $script:Warnings.Add($msg)
}
function Stop-Setup([string]$msg, [int]$code = 1) { throw [SetupStop]::new($msg, $code) }

function Test-Assumed([string]$what) { return ($DryRun -and ($AssumeMissing -contains $what)) }

# ------------------------------------------------------------------ system helpers
function Update-SessionPath {
    # Pick up PATH changes made by installers without reopening the window.
    $parts = @()
    foreach ($scope in 'Machine', 'User') {
        $p = [Environment]::GetEnvironmentVariable('Path', $scope)
        if ($p) { $parts += $p -split ';' }
    }
    $parts += $env:Path -split ';'
    $seen = @{}
    $clean = foreach ($p in $parts) {
        $t = $p.Trim()
        if ($t -and -not $seen.ContainsKey($t.ToLowerInvariant())) { $seen[$t.ToLowerInvariant()] = $true; $t }
    }
    $env:Path = $clean -join ';'
}

function Test-Winget {
    return [bool](Get-Command winget -ErrorAction SilentlyContinue)
}

function Invoke-Winget([string]$id, [string[]]$extra = @()) {
    $wingetArgs = @('install', '-e', '--id', $id, '--accept-package-agreements', '--accept-source-agreements') + $extra
    if ($DryRun) { Write-Dry ("run: winget " + ($wingetArgs -join ' ')); return $true }
    if (-not (Test-Winget)) { return $false }
    Write-Info ("Running: winget " + ($wingetArgs -join ' '))
    Write-Info 'This can take a few minutes. A Windows permission prompt may appear.'
    $proc = Start-Process -FilePath 'winget' -ArgumentList $wingetArgs -NoNewWindow -Wait -PassThru
    $rc = $proc.ExitCode
    # 0 = installed; -1978335189 (0x8A15002B) = already installed / no newer version.
    if ($rc -ne 0 -and $rc -ne -1978335189) {
        Add-Warning "winget finished with code $rc for $id."
        return $false
    }
    return $true
}

function Get-PythonVersionInfo([string]$exe, [string[]]$prefix = @()) {
    # Returns @{Version='3.12'; Path='C:\...\python.exe'} or $null.
    if (-not $exe) { return $null }
    # The path is printed as hex UTF-8: a user folder with Turkish letters (C:\Users\<name>) would otherwise be
    # garbled between Python's and PowerShell's code pages, and Python 3.12 not be found.
    try {
        $out = & $exe @prefix -c 'import sys; print(''%d.%d'' % sys.version_info[:2]); print(sys.executable.encode(''utf-8'').hex())' 2>$null
    } catch { return $null }
    if ($LASTEXITCODE -ne 0 -or -not $out) { return $null }
    $lines = @($out)
    if ($lines.Count -lt 2) { return $null }
    $hex = $lines[1].Trim()
    if ($hex -notmatch '^([0-9a-f]{2})+$') { return $null }
    $bytes = [byte[]]::new($hex.Length / 2)
    for ($i = 0; $i -lt $bytes.Length; $i++) { $bytes[$i] = [Convert]::ToByte($hex.Substring(2 * $i, 2), 16) }
    return @{ Version = $lines[0].Trim(); Path = [Text.Encoding]::UTF8.GetString($bytes) }
}

function Find-Python312 {
    if (Test-Assumed 'python') { return $null }
    # 1) The Python launcher.
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $info = Get-PythonVersionInfo 'py' @('-3.12')
        if ($info -and $info.Version -eq '3.12') { return $info.Path }
    }
    # 2) Standard install folders (works even before PATH is refreshed).
    $candidates = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'),
        (Join-Path $env:ProgramFiles 'Python312\python.exe')
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) {
            $info = Get-PythonVersionInfo $c
            if ($info -and $info.Version -eq '3.12') { return $info.Path }
        }
    }
    # 3) Any python.exe on PATH (skipping the Microsoft Store placeholder).
    foreach ($cmd in @(Get-Command python -All -ErrorAction SilentlyContinue)) {
        if ($cmd.Source -like '*\WindowsApps\*') { continue }
        $info = Get-PythonVersionInfo $cmd.Source
        if ($info -and $info.Version -eq '3.12') { return $info.Path }
    }
    return $null
}

function Get-MissingFfmpegTools {
    $missing = @()
    foreach ($tool in 'ffmpeg', 'ffprobe', 'ffplay') {
        if ((Test-Assumed 'ffmpeg') -or -not (Get-Command $tool -ErrorAction SilentlyContinue)) { $missing += $tool }
    }
    return $missing
}

function Invoke-Checked([string]$what, [string]$exe, [string[]]$arguments) {
    if ($DryRun) { Write-Dry ("run: `"$exe`" " + ($arguments -join ' ')); return }
    & $exe @arguments
    if ($LASTEXITCODE -ne 0) { Stop-Setup "$what failed (exit code $LASTEXITCODE). Check your internet connection and run setup.bat again." }
}

# ------------------------------------------------------------------ steps
function Step-Python {
    Write-Step 1 'Python 3.12'
    $py = Find-Python312
    if ($py) { Write-Ok "Found Python 3.12: $py"; return $py }

    Write-Info 'Python 3.12 was not found. Installing it for this user with winget...'
    if (-not $DryRun -and -not (Test-Winget)) {
        Stop-Setup ("winget (App Installer) is not available on this PC.`n" +
            "  Install Python 3.12 (64-bit) from https://www.python.org/downloads/windows/`n" +
            "  (tick 'Add python.exe to PATH'), then run setup.bat again.")
    }
    if (-not (Invoke-Winget 'Python.Python.3.12' @('--scope', 'user'))) {
        Stop-Setup 'Installing Python 3.12 with winget failed. Install it from https://www.python.org/downloads/windows/ and run setup.bat again.'
    }
    if ($DryRun) { return '<python 3.12 after install>' }
    Update-SessionPath
    $py = Find-Python312
    if (-not $py) {
        Stop-Setup ("Python 3.12 was installed, but this window cannot see it yet.`n" +
            '  Please close this window and double-click setup.bat again.') 2
    }
    Write-Ok "Installed Python 3.12: $py"
    return $py
}

function Step-Ffmpeg {
    Write-Step 2 'ffmpeg, ffprobe and ffplay (video tools)'
    $missing = @(Get-MissingFfmpegTools)
    if ($missing.Count -eq 0) {
        Write-Ok ('Found: ' + (Get-Command ffmpeg).Source)
        return
    }
    Write-Info ('Missing: ' + ($missing -join ', ') + '. Installing FFmpeg with winget...')
    if (-not $DryRun -and -not (Test-Winget)) {
        Add-Warning ('winget is not available, so FFmpeg could not be installed automatically. ' +
            'Download a Windows build from https://www.gyan.dev/ffmpeg/builds/, add its bin folder to PATH, then run setup.bat again.')
        return
    }
    if (-not (Invoke-Winget 'Gyan.FFmpeg')) {
        Add-Warning 'Installing FFmpeg with winget failed. Install it manually (https://www.gyan.dev/ffmpeg/builds/) and run setup.bat again.'
        return
    }
    if ($DryRun) { return }
    Update-SessionPath
    $missing = @(Get-MissingFfmpegTools)
    if ($missing.Count -eq 0) {
        Write-Ok ('Installed: ' + (Get-Command ffmpeg).Source)
    } else {
        Add-Warning ('FFmpeg was installed but ' + ($missing -join ', ') + ' is not visible yet. ' +
            'Restart Windows (or sign out and in) and run setup.bat again to confirm.')
    }
}

function Step-Venv([string]$python) {
    Write-Step 3 'Python environment (.venv) and packages'
    $haveVenv = (Test-Path $VenvPy) -and -not (Test-Assumed 'venv')
    if ($haveVenv) {
        $info = Get-PythonVersionInfo $VenvPy
        if ($info -and $info.Version -eq '3.12') {
            Write-Ok "Existing .venv uses Python 3.12 - keeping it."
        } else {
            $ver = if ($info) { $info.Version } else { 'unknown/broken' }
            Write-Info "Existing .venv uses Python $ver; it will be rebuilt with 3.12."
            if ($DryRun) { Write-Dry "delete $VenvDir" }
            else {
                Remove-Item -LiteralPath $VenvDir -Recurse -Force -ErrorAction SilentlyContinue
                if (Test-Path $VenvDir) { Stop-Setup "Could not remove the old .venv folder. Close Subtitle Translator and run setup.bat again." }
            }
            $haveVenv = $false
        }
    }
    if (-not $haveVenv) {
        Write-Info 'Creating .venv ...'
        Invoke-Checked 'Creating the Python environment' $python @('-m', 'venv', $VenvDir)
        if (-not $DryRun) { Write-Ok 'Created .venv' }
    }

    Write-Info 'Updating pip ...'
    Invoke-Checked 'Updating pip' $VenvPy (@('-m', 'pip', 'install', '--upgrade', 'pip', '--quiet') + $PipOpts)

    Write-Info 'Installing packages from requirements.txt (first time: about 1.5 GB download, 2.3 GB on disk) ...'
    Write-Info 'The first time this takes 5-20 minutes (longer on a slow connection); the window may show no new lines for several minutes while packages are unpacked. Please wait.'
    if ($DryRun -and $haveVenv) {
        # Read-only: shows what pip would add or change in the existing .venv.
        Write-Info 'pip install --dry-run (nothing is changed):'
        & $VenvPy -m pip install --dry-run --disable-pip-version-check -r $Reqs 2>&1 |
            ForEach-Object { "$_" } | Where-Object { $_ -notlike 'Requirement already satisfied*' } |
            ForEach-Object { Write-Info $_ }
        if ($LASTEXITCODE -ne 0) { Add-Warning "pip --dry-run reported a problem (exit code $LASTEXITCODE)." }
    } else {
        Invoke-Checked 'Installing packages' $VenvPy (@('-m', 'pip', 'install', '-r', $Reqs) + $PipOpts)
    }
    if (-not $DryRun) { Write-Ok 'Packages are installed.' }
}

$VerifyCode = @'
import importlib, sys
failed = []
for name in ("tkinter", "faster_whisper", "ctranslate2", "av", "deep_translator", "tkinterdnd2"):
    try:
        importlib.import_module(name)
    except Exception as e:
        failed.append(name)
        print("IMPORT-FAIL %s: %s" % (name, e))
try:
    import ctranslate2
    print("CUDA-DEVICES %d" % ctranslate2.get_cuda_device_count())
except Exception as e:
    print("CUDA-DEVICES 0")
sys.exit(1 if failed else 0)
'@

function Step-Verify {
    Write-Step 4 'Checking the installation'
    if (-not (Test-Path $VenvPy) -or (Test-Assumed 'venv')) {
        if ($DryRun) { Write-Dry 'check that all packages import and whether a CUDA GPU is visible'; return }
        Stop-Setup '.venv is missing after installation.'
    }
    $out = @($VerifyCode | & $VenvPy - 2>&1 | ForEach-Object { "$_" })
    $rc = $LASTEXITCODE
    foreach ($line in $out) {
        if ($line -like 'IMPORT-FAIL*') { Write-Host "  FAIL  $($line.Substring(12))" -ForegroundColor Red }
    }
    if ($rc -ne 0) {
        if ($out -match 'IMPORT-FAIL tkinter') {
            Stop-Setup 'Python was installed without Tk (tkinter). Re-install Python 3.12 with "tcl/tk and IDLE" ticked, then run setup.bat again.'
        }
        Stop-Setup 'Some packages failed to load. Run setup.bat again; if it keeps failing, delete the .venv folder and retry.'
    }
    Write-Ok 'All packages load.'
    $gpu = $out | Where-Object { $_ -like 'CUDA-DEVICES *' } | Select-Object -First 1
    $count = 0
    if ($gpu) { [int]::TryParse($gpu.Substring(13), [ref]$count) | Out-Null }
    if ($count -gt 0) { Write-Ok "NVIDIA GPU detected ($count) - speech recognition will use the GPU." }
    else { Write-Info 'No NVIDIA GPU detected - the app will use the CPU (works, but slower).' }
}

function New-AppShortcut([string]$folder) {
    if (-not $folder -or -not (Test-Path $folder)) { Add-Warning "Shortcut folder not found: $folder"; return }
    $lnkPath = Join-Path $folder "$AppName.lnk"
    if ($DryRun) { Write-Dry "create shortcut $lnkPath -> $RunBat"; return }
    $shell = New-Object -ComObject WScript.Shell
    $lnk = $shell.CreateShortcut($lnkPath)
    $lnk.TargetPath = $RunBat
    $lnk.WorkingDirectory = $AppDir
    $lnk.Description = 'Transcribe, translate and burn subtitles into videos'
    $lnk.WindowStyle = 7   # minimized: run.bat only starts the app and closes
    if (Test-Path -LiteralPath $IconFile) { $lnk.IconLocation = "$IconFile,0" }
    $lnk.Save()
    # WScript.Shell stores paths in the ANSI code page: Turkish letters (dotless i, s-cedilla, ...) become
    # '?'/'i' and the shortcut points nowhere. Set the paths again through the Unicode
    # Shell.Application link object.
    try {
        $link = (New-Object -ComObject Shell.Application).NameSpace($folder).ParseName("$AppName.lnk").GetLink
        $link.Path = $RunBat
        $link.WorkingDirectory = $AppDir
        if (Test-Path -LiteralPath $IconFile) { $link.SetIconLocation($IconFile, 0) }
        $link.Save()
        if (-not (Test-Path -LiteralPath $link.Path)) { throw 'target not found' }
    } catch {
        Add-Warning "The shortcut $lnkPath may not work (folder name with special letters?). Start the app with run.bat in $AppDir instead."
        return
    }
    Write-Ok "Shortcut: $lnkPath"
}

function Step-Shortcuts {
    Write-Step 5 'Shortcuts'
    if ($SkipShortcuts) { Write-Info 'Skipped (-SkipShortcuts).'; return }
    if (-not (Test-Path $RunBat)) { Add-Warning 'run.bat is missing, so no shortcuts were created.'; return }
    New-AppShortcut ([Environment]::GetFolderPath('Desktop'))
    New-AppShortcut ([Environment]::GetFolderPath('Programs'))
}

function Unblock-AppFiles {
    # Files from a downloaded ZIP carry a "came from the internet" mark that makes Windows
    # show security prompts when starting run.bat. Remove it from the app's own files.
    $files = @(Get-ChildItem -LiteralPath $AppDir -File -ErrorAction SilentlyContinue)
    $files += @(Get-ChildItem -LiteralPath (Join-Path $AppDir 'assets') -File -ErrorAction SilentlyContinue)
    $files += @(Get-ChildItem -LiteralPath (Join-Path $AppDir 'docs') -File -ErrorAction SilentlyContinue)
    $marked = @($files | Where-Object { Get-Item -LiteralPath $_.FullName -Stream Zone.Identifier -ErrorAction SilentlyContinue })
    if ($marked.Count -eq 0) { return }
    if ($DryRun) { Write-Dry "unblock $($marked.Count) downloaded file(s)"; return }
    $marked | Unblock-File -ErrorAction SilentlyContinue
    Write-Info "Unblocked $($marked.Count) downloaded file(s)."
}

# ------------------------------------------------------------------ main
$exitCode = 0
try {
    if ($AssumeMissing.Count -gt 0 -and -not $DryRun) { Stop-Setup '-AssumeMissing can only be used together with -DryRun.' }
    foreach ($a in $AssumeMissing) { if (@('python', 'ffmpeg', 'venv') -notcontains $a) { Stop-Setup "-AssumeMissing: unknown value '$a' (use python, ffmpeg, venv)." } }
    Write-Host "=== $AppName setup ===" -ForegroundColor White
    Write-Host "Folder: $AppDir"
    if ($DryRun) { Write-Host 'DRY RUN: nothing will be installed or changed.' -ForegroundColor Magenta }
    if (-not [Environment]::Is64BitOperatingSystem) { Stop-Setup 'Subtitle Translator needs 64-bit Windows.' }
    if (-not (Test-Path $Reqs)) { Stop-Setup "requirements.txt not found in $AppDir. Run setup.bat from the app folder." }

    Unblock-AppFiles
    $python = Step-Python
    Step-Ffmpeg
    Step-Venv $python
    Step-Verify
    Step-Shortcuts

    Write-Host ''
    if ($script:Warnings.Count -gt 0) {
        Write-Host 'Setup finished with warnings:' -ForegroundColor Yellow
        foreach ($w in $script:Warnings) { Write-Host "  - $w" -ForegroundColor Yellow }
        $exitCode = 3
    } elseif ($DryRun) {
        Write-Host 'Dry run finished. Nothing was changed.' -ForegroundColor Magenta
    } else {
        Write-Host 'Setup finished successfully!' -ForegroundColor Green
        Write-Host "Start the app with the '$AppName' shortcut (or run.bat)."
        Write-Host 'The first transcription/translation downloads the AI models (about 3 GB, once).'
    }
}
catch [SetupStop] {
    Write-Host ''
    Write-Host "SETUP STOPPED: $($_.Exception.Message)" -ForegroundColor Red
    $exitCode = $_.Exception.Code
}
catch {
    Write-Host ''
    Write-Host "SETUP FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray
    $exitCode = 1
}
exit $exitCode
