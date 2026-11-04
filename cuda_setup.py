"""CUDA DLL setup for pip-installed NVIDIA libraries (nvidia-cublas-cu12, nvidia-cudnn-cu12).

CTranslate2 (used by faster-whisper and the NLLB translator) loads cuBLAS/cuDNN
at runtime. When those come from pip wheels, their DLLs live in
site-packages/nvidia/*/bin, which Windows does not search by default.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Callable

_dll_handles = []  # keep add_dll_directory handles alive
_dlls_prepared = False
_cuda_ok: bool | None = None


def prepare_cuda_dlls(log: Callable[[str], None] = print) -> None:
    """Make site-packages/nvidia/*/bin folders findable by the DLL loader (once)."""
    global _dlls_prepared
    if _dlls_prepared or sys.platform != "win32":
        return
    _dlls_prepared = True

    roots = []
    spec = importlib.util.find_spec("nvidia")
    if spec is not None and spec.submodule_search_locations:
        roots = list(spec.submodule_search_locations)

    found = []
    for root in roots:
        for sub in Path(root).iterdir():
            bin_dir = sub / "bin"
            if bin_dir.is_dir():
                found.append(str(bin_dir))

    for d in found:
        try:
            _dll_handles.append(os.add_dll_directory(d))
        except OSError:
            pass
    if found:
        os.environ["PATH"] = os.pathsep.join(found) + os.pathsep + os.environ.get("PATH", "")
        log(f"Registered {len(found)} NVIDIA DLL folder(s).")
    else:
        log("No pip-installed NVIDIA DLL folders found.")


def cuda_usable(log: Callable[[str], None] = print) -> bool:
    """True if a CUDA GPU and the cuBLAS/cuDNN DLLs are available (result cached).

    A cheap pre-check so a missing DLL doesn't crash the process mid-run.
    """
    global _cuda_ok
    if _cuda_ok is None:
        prepare_cuda_dlls(log)
        _cuda_ok = _check_cuda(log)
    return _cuda_ok


def _check_cuda(log: Callable[[str], None]) -> bool:
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() < 1:
            log("No CUDA device detected.")
            return False
    except Exception as e:  # noqa: BLE001
        log(f"CUDA check failed: {e}")
        return False

    if sys.platform == "win32":
        import ctypes

        for dll in ("cublas64_12.dll", "cudnn64_9.dll"):
            try:
                ctypes.WinDLL(dll)
            except OSError:
                log(f"CUDA library {dll} could not be loaded.")
                return False
    return True
