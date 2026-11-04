# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the standalone Subtitle Translator (one-folder build).
# Build with build_exe.bat  ->  dist\SubtitleTranslator\SubtitleTranslator.exe
#
# Layout: contents_directory="." puts everything next to the exe (no _internal folder).
# That way code using Path(__file__).parent finds models/, glossary.txt, assets/ and
# settings.json in the exe's folder exactly as when running from source.
# AI models are NOT bundled: they download into dist\SubtitleTranslator\models on first run.
# ffmpeg/ffprobe/ffplay are NOT bundled: install them on the PC (setup.bat or
# "winget install Gyan.FFmpeg"), or copy the three exe files next to SubtitleTranslator.exe.

import glob
import os
import sysconfig

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

HERE = os.path.abspath(SPECPATH)
SITE = sysconfig.get_paths()["purelib"]

# App modules. app.py imports most of them, but list them so lazy/dynamic imports are kept.
# i18n_* text tables are imported by name at runtime, so PyInstaller must be told about them.
APP_MODULES = ["editor", "engine", "translation", "subtitles", "glossary", "cuda_setup",
               "i18n", "i18n_app", "i18n_editor", "i18n_engine", "transcript"]
hiddenimports = []
for mod in APP_MODULES:
    if os.path.exists(os.path.join(HERE, mod + ".py")):
        hiddenimports.append(mod)
    else:
        print(f"[spec] note: {mod}.py not found, skipped")
hiddenimports += ["faster_whisper", "ctranslate2", "deep_translator", "tkinterdnd2", "av", "docx"]

datas = []
for name in ("glossary.example.txt", "README.md", "README.en.md"):  # READMEs: Help > User guide
    if os.path.exists(os.path.join(HERE, name)):
        datas.append((os.path.join(HERE, name), "."))
for name in ("icon.ico", "icon.png"):
    datas.append((os.path.join(HERE, "assets", name), "assets"))
datas += collect_data_files("faster_whisper")    # assets/silero_vad_v6.onnx (voice detection)
datas += collect_data_files("docx")              # python-docx's default.docx template (transcript export)
# tkinterdnd2 brings its own PyInstaller hook (bundles tkdnd for win-x64 only).

binaries = collect_dynamic_libs("ctranslate2")   # ctranslate2.dll, libiomp5md.dll, ...

# NVIDIA CUDA libraries from the pip wheels. They keep their site-packages layout
# (nvidia\cublas\bin, nvidia\cudnn\bin, nvidia\cuda_nvrtc\bin): PyInstaller's dependency
# scanner puts linked DLLs there anyway (flattening them duplicated ~0.8 GB), and
# cuda_setup.prepare_cuda_dlls() finds these folders in the exe just like in the venv.
# Skipped: nvblas (BLAS wrapper, unused) and the ".alt" nvrtc variant.
NVIDIA_DLLS = [
    "nvidia/cublas/bin/cublas64_*.dll",
    "nvidia/cublas/bin/cublasLt64_*.dll",
    "nvidia/cudnn/bin/cudnn*.dll",
    "nvidia/cuda_nvrtc/bin/nvrtc64_*_0.dll",
    "nvidia/cuda_nvrtc/bin/nvrtc-builtins64_*.dll",
]
for pattern in NVIDIA_DLLS:
    found = glob.glob(os.path.join(SITE, *pattern.split("/")))
    if not found:
        print(f"[spec] WARNING: no files for {pattern} - the exe will run on CPU only")
    binaries += [(path, os.path.relpath(os.path.dirname(path), SITE)) for path in found]

# Runtime hook: in the windowed exe sys.stdout/sys.stderr are None, and progress bars
# (tqdm, used by huggingface_hub when downloading the NLLB model) crash on the first
# write ("'NoneType' object has no attribute 'write'"). Send that output to
# SubtitleTranslator.log next to the exe instead (previous run: SubtitleTranslator.old.log).
RTH_STDIO = os.path.join(workpath, "rth_stdio.py")
os.makedirs(workpath, exist_ok=True)
with open(RTH_STDIO, "w", encoding="utf-8") as f:
    f.write(r'''
import os, sys
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
if sys.stdout is None or sys.stderr is None:
    _dir = os.path.dirname(sys.executable)
    _log = os.path.join(_dir, "SubtitleTranslator.log")
    try:
        if os.path.exists(_log):
            os.replace(_log, os.path.join(_dir, "SubtitleTranslator.old.log"))
        _f = open(_log, "w", encoding="utf-8", errors="replace", buffering=1)
    except OSError:
        _f = open(os.devnull, "w", encoding="utf-8")
    if sys.stdout is None:
        sys.stdout = _f
    if sys.stderr is None:
        sys.stderr = _f
''')

ANALYSIS_OPTS = dict(
    pathex=[HERE],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=["torch", "tensorflow", "transformers", "matplotlib", "IPython", "pytest"],
    noarchive=False,
)

# 1) SubtitleTranslator.exe - the windowed app.
a = Analysis([os.path.join(HERE, "app.py")], runtime_hooks=[RTH_STDIO], **ANALYSIS_OPTS)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="SubtitleTranslator",
    icon=os.path.join(HERE, "assets", "icon.ico"),
    console=False,            # GUI app: no console window
    upx=False,                # UPX breaks/slows the large CUDA DLLs
    contents_directory=".",
)

# 2) SubtitleTranslatorCLI.exe - the engine command line (same options as
#    "python engine.py ..."), with a console. Shares all DLLs with the app (~10 MB extra).
#    Also useful for troubleshooting: it prints every log message.
b = Analysis([os.path.join(HERE, "engine.py")], runtime_hooks=[], **ANALYSIS_OPTS)
pyz_cli = PYZ(b.pure)
exe_cli = EXE(
    pyz_cli,
    b.scripts,
    [],
    exclude_binaries=True,
    name="SubtitleTranslatorCLI",
    icon=os.path.join(HERE, "assets", "icon.ico"),
    console=True,
    upx=False,
    contents_directory=".",
)

coll = COLLECT(
    exe,
    exe_cli,
    a.binaries,
    a.datas,
    b.binaries,
    b.datas,
    strip=False,
    upx=False,
    name="SubtitleTranslator",
)
