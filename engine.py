"""Subtitle Translator engine: video -> speech recognition -> subtitles -> translation -> burn.

Orchestrates the other modules (see docs/ARCHITECTURE.md):
  subtitles.py   cue building, wrapping, SRT/VTT files
  translation.py translators (NLLB offline, Google online) and glossary enforcement
  glossary.py    the user's glossary of names and terms
  cuda_setup.py  making the pip-installed NVIDIA DLLs loadable
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import cuda_setup
import glossary as glossary_mod
import subtitles
import translation
from translation import Cancelled, TRANSLATORS, DEFAULT_TRANSLATOR  # noqa: F401  (re-exported)

# --------------------------------------------------------------------------
# Public constants
# --------------------------------------------------------------------------

# Display name -> Whisper language code.
LANGUAGES: dict[str, str] = {
    "Turkish": "tr",
    "English": "en",
    "German": "de",
    "French": "fr",
    "Spanish": "es",
    "Italian": "it",
    "Portuguese": "pt",
    "Dutch": "nl",
    "Russian": "ru",
    "Ukrainian": "uk",
    "Polish": "pl",
    "Czech": "cs",
    "Romanian": "ro",
    "Hungarian": "hu",
    "Greek": "el",
    "Bulgarian": "bg",
    "Swedish": "sv",
    "Norwegian": "no",
    "Danish": "da",
    "Finnish": "fi",
    "Arabic": "ar",
    "Persian": "fa",
    "Hebrew": "he",
    "Hindi": "hi",
    "Urdu": "ur",
    "Bengali": "bn",
    "Chinese": "zh",
    "Japanese": "ja",
    "Korean": "ko",
    "Indonesian": "id",
    "Malay": "ms",
    "Vietnamese": "vi",
    "Thai": "th",
    "Azerbaijani": "az",
    "Kazakh": "kk",
}

MODEL_SIZES: list[str] = ["tiny", "base", "small", "medium", "large-v3-turbo"]
DEFAULT_MODEL = "large-v3-turbo"

LINE_WIDTH = 42           # characters per subtitle line in SRT files
PORTRAIT_LINE_WIDTH = 28  # narrower lines when burning into vertical videos

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# Progress budget for process_video (fractions of the whole job).
_P_AUDIO, _P_TRANSCRIBE, _P_TRANSLATE = 0.02, 0.60, 0.85


@dataclass
class BurnStyle:
    position: str = "bottom"   # "bottom" | "top"
    font_size: str = "auto"    # "auto" | "small" | "medium" | "large"
    box: bool = False          # semi-transparent background box behind the text
    font: str = "Arial"


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _one_line(error: BaseException) -> str:
    """Error text on one line (Windows/CUDA messages can span several lines)."""
    return " ".join(str(error).split())


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled("Cancelled by user.")


def _resolve_lang(value: str | None) -> str | None:
    """Accept either a code ('tr') or a display name ('Turkish'); None/'auto' -> None."""
    if not value or value.lower() == "auto":
        return None
    for name, code in LANGUAGES.items():
        if value.lower() == name.lower():
            return code
    return value.lower().split("-")[0]


def _scaled(progress: Callable[[float], None], start: float, end: float) -> Callable[[float], None]:
    """Map a sub-task's 0..1 progress onto [start, end] of the overall bar."""
    return lambda p: progress(start + (end - start) * max(0.0, min(p, 1.0)))


def _tool_missing(cmd: list[str]) -> RuntimeError:
    return RuntimeError(f"FFmpeg is missing ({cmd[0]} not found). Run setup.bat again.\n"
                        "If it still fails, restart Windows and try once more.")


def _run_tool(cmd: list[str]) -> subprocess.CompletedProcess:
    """Run ffmpeg/ffprobe and capture its output; a clear error if it isn't installed."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", creationflags=_NO_WINDOW)
    except FileNotFoundError:
        raise _tool_missing(cmd) from None


def _start_tool(cmd: list[str], **kwargs) -> subprocess.Popen:
    """Start ffmpeg in the background (text output); a clear error if it isn't installed."""
    try:
        return subprocess.Popen(cmd, stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                errors="replace", creationflags=_NO_WINDOW, **kwargs)
    except FileNotFoundError:
        raise _tool_missing(cmd) from None


def _kill_tree(proc: subprocess.Popen) -> None:
    """Stop a process and its children. 'ffmpeg' may be a launcher (e.g. a Chocolatey shim)
    that runs the real ffmpeg.exe as a child, which proc.kill() alone would leave running."""
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True, creationflags=_NO_WINDOW)
    proc.kill()
    proc.wait()


def _remove_dir(path: str) -> None:
    """Delete a temp folder. Right after a killed ffmpeg, Windows may still hold its files
    (or the folder as its working directory) for a moment, so try for up to 3 seconds."""
    for _ in range(15):
        shutil.rmtree(path, ignore_errors=True)
        if not os.path.exists(path):
            return
        time.sleep(0.2)


def _audio_streams(video_path: str) -> int:
    """Number of audio streams; RuntimeError if ffprobe can't read the file at all."""
    result = _run_tool(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                        "-of", "csv=p=0", video_path])
    types = result.stdout.split()
    if result.returncode != 0 or not types:
        raise RuntimeError("Cannot open this file as a video (damaged, incomplete or not a video).\n"
                           + result.stderr.strip()[-1500:])
    return types.count("audio")


def _video_size(video_path: str) -> tuple[int, int]:
    """Displayed width and height of the main picture (phone videos are often stored
    landscape with a 90° rotation flag; ffmpeg turns them upright when burning)."""
    try:
        # "V" = real video streams, not cover art (attached pictures).
        out = _run_tool(["ffprobe", "-v", "error", "-select_streams", "V:0", "-show_entries",
                         "stream=width,height:stream_tags=rotate:stream_side_data=rotation",
                         "-of", "json", video_path]).stdout
        stream = json.loads(out)["streams"][0]
        w, h = int(stream["width"]), int(stream["height"])
        rotation = stream.get("tags", {}).get("rotate", 0)
        for side in stream.get("side_data_list", []):
            rotation = side.get("rotation", rotation)
        return (h, w) if round(float(rotation)) % 180 == 90 else (w, h)
    except Exception:  # noqa: BLE001
        return 1920, 1080


def _media_duration(path: str) -> float:
    try:
        out = _run_tool(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                         "-of", "csv=p=0", path]).stdout.strip()
        return float(out)
    except Exception:  # noqa: BLE001
        return 0.0


# --------------------------------------------------------------------------
# Audio extraction and transcription
# --------------------------------------------------------------------------

_MODEL_CACHE: dict = {}


def extract_audio(video_path: str, wav_path: str, log: Callable[[str], None],
                  cancel: threading.Event | None = None) -> None:
    if not _audio_streams(video_path):
        raise RuntimeError("This video has no sound track, so there is no speech to subtitle.")
    log("Extracting audio with ffmpeg...")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-i", video_path, "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000", "-f", "wav", wav_path]
    # Takes about a minute for a 2-hour recording: keep it cancellable.
    proc = _start_tool(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        while True:
            try:
                _, err = proc.communicate(timeout=0.5)
                break
            except subprocess.TimeoutExpired:
                _check_cancel(cancel)
    finally:
        if proc.poll() is None:
            _kill_tree(proc)
    if proc.returncode != 0 or not os.path.exists(wav_path):
        raise RuntimeError("Could not read the sound of this video (ffmpeg failed).\n" + err.strip()[-1500:])


_MODEL_DOWNLOAD_SIZES = {"tiny": "75 MB", "base": "145 MB", "small": "480 MB",
                         "medium": "1.5 GB", "large-v3-turbo": "1.6 GB"}


def _model_files(model_size: str, log: Callable[[str], None]) -> str:
    """Folder of the Whisper model, downloaded (once) if needed. Raises a clear error offline."""
    from faster_whisper.utils import download_model

    try:
        return download_model(model_size, local_files_only=True)
    except Exception:  # noqa: BLE001  (not downloaded yet)
        pass
    size = _MODEL_DOWNLOAD_SIZES.get(model_size, "")
    log(f"Downloading the speech recognition model '{model_size}' ({size}, only once). "
        "This can take several minutes...")
    try:
        with translation.download_status("the speech recognition model", size, log):
            path = download_model(model_size)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("Could not download the speech recognition model (no internet?).\n"
                           "The internet is needed only the first time. Check it and try again.\n"
                           f"{type(e).__name__}: {e}") from e
    log("Speech recognition model downloaded.")
    return path


def _load_model(model_size: str, device: str, log: Callable[[str], None]):
    key = (model_size, device)
    if key not in _MODEL_CACHE:
        from faster_whisper import WhisperModel

        path = _model_files(model_size, log)
        compute_type = "int8_float16" if device == "cuda" else "int8"
        log(f"Loading speech recognition model '{model_size}' on {device.upper()}...")
        _MODEL_CACHE[key] = WhisperModel(path, device=device, compute_type=compute_type)
    return _MODEL_CACHE[key]


# Lines Whisper "hears" in music or silence: credits from its training subtitles.
_CREDIT_JUNK = re.compile(
    r"altyaz[ıi]|amara\.org|untertitel|sous-titr|subtit(?:le|ling)s? by|transcri(?:bed|ption) by"
    r"|www\.|\bM\.K\.", re.IGNORECASE)
_MIN_WORD_PROBABILITY = 0.3   # real speech scores 0.8-1.0; noise "heard" as words ~0.0-0.1


def _clock(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m // 60}:{m % 60:02d}:{s:02d}" if m >= 60 else f"{m}:{s:02d}"


def _hallucination(seg) -> str | None:
    """Why a Whisper segment is not real speech (None if it looks real)."""
    words = seg.words or []
    if words and sum(w.probability for w in words) / len(words) < _MIN_WORD_PROBABILITY:
        return "unclear sound"
    if len(seg.text) < 60 and _CREDIT_JUNK.search(seg.text):
        return "subtitle credit"
    return None


def _run_transcription(model, wav_path, source_lang, prompt, log, progress, cancel):
    segments_iter, info = model.transcribe(
        wav_path,
        language=source_lang,
        vad_filter=True,
        beam_size=5,
        word_timestamps=True,               # needed for well-timed cues
        initial_prompt=prompt or None,      # glossary names help recognition
        condition_on_previous_text=False,   # avoids repetition loops on long recordings
    )
    if source_lang is None:
        log(f"Detected language: {info.language} (probability {info.language_probability:.2f})")
        if info.language_probability < 0.6:
            log("  Not sure about the spoken language. If the subtitles look wrong, choose the "
                "spoken language instead of Auto-detect.")

    duration = info.duration or 0.0
    segments = []
    for seg in segments_iter:
        _check_cancel(cancel)
        text = " ".join(seg.text.split())
        reason = _hallucination(seg) if text else None
        if reason:
            log(f"  Skipped {reason} at {_clock(seg.start)} (not speech?): {text[:60]}")
        elif segments and text == segments[-1]["text"] and len(text) > 15 and \
                seg.start - segments[-1]["end"] < 2:
            log(f"  Skipped a repeated line at {_clock(seg.start)}: {text[:60]}")
        elif text:
            words = [{"start": w.start, "end": w.end, "word": w.word} for w in (seg.words or [])]
            segments.append({"start": seg.start, "end": seg.end, "text": text, "words": words})
        if duration > 0:
            progress(min(seg.end / duration, 1.0))
    progress(1.0)
    return segments, info.language


def transcribe(wav_path: str, source_lang: str | None, model_size: str, prompt: str,
               log: Callable[[str], None], progress: Callable[[float], None],
               cancel: threading.Event | None):
    """Transcribe on the GPU if possible, otherwise on CPU. Returns (segments, language)."""
    cuda_setup.prepare_cuda_dlls(log)
    _model_files(model_size, log)   # a failed download must not look like a GPU problem
    if cuda_setup.cuda_usable(log):
        try:
            model = _load_model(model_size, "cuda", log)
            log("Transcribing on GPU...")
            return _run_transcription(model, wav_path, source_lang, prompt, log, progress, cancel)
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"GPU transcription failed ({type(e).__name__}: {_one_line(e)}). Falling back to CPU.")
            _MODEL_CACHE.pop((model_size, "cuda"), None)
            progress(0.0)
    else:
        log("Using CPU (slower).")

    try:
        model = _load_model(model_size, "cpu", log)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Could not load the speech recognition model ({type(e).__name__}: {_one_line(e)})") from e
    log("Transcribing on CPU...")
    return _run_transcription(model, wav_path, source_lang, prompt, log, progress, cancel)


# --------------------------------------------------------------------------
# Burning subtitles
# --------------------------------------------------------------------------

_FONT_SIZES = {"small": 14, "medium": 18, "large": 22, "auto": 17}


def _force_style(style: BurnStyle, width: int, height: int) -> str:
    """libass style overrides. libass scales fonts by video height, so portrait
    videos (tall and narrow) need a smaller size to fit the width."""
    size = _FONT_SIZES.get(style.font_size, _FONT_SIZES["auto"])
    portrait = height > width
    if portrait:
        size *= max(0.45, ((width / height) / (16 / 9)) ** 0.5)
    # Characters that would break ffmpeg's filter syntax can't be part of a font name.
    font = re.sub(r"[\\',:;=\[\]]", "", style.font or "").strip() or "Arial"
    parts = [
        f"FontName={font}",
        f"FontSize={size:.1f}",
        # libass reads force_style alignment the old SSA way: 2 = bottom centre,
        # 6 = top centre (the numpad value 8 put "top" text at the middle left).
        f"Alignment={6 if style.position == 'top' else 2}",
        f"MarginV={40 if portrait else 20}",
    ]
    if style.box:
        # BorderStyle 3 = opaque box; BackColour is &HAABBGGRR (80 = half transparent).
        parts += ["BorderStyle=3", "Outline=1", "Shadow=0", "BackColour=&H80000000"]
    else:
        parts += ["BorderStyle=1", "Outline=1.5", "Shadow=0.5"]
    return ",".join(parts)


def burn_video(video_path: str, srt_path: str, out_path: str | None = None,
               style: BurnStyle | None = None, log: Callable[[str], None] = print,
               progress: Callable[[float], None] = lambda p: None,
               cancel: threading.Event | None = None) -> str:
    """Hard-code an SRT into a new MP4 and return its path. Progress is 0..1."""
    style = style or BurnStyle()
    if out_path is None:
        srt = Path(srt_path)
        out_path = str(srt.with_name(srt.stem + ".subtitled.mp4"))
    log(f"Burning subtitles into {Path(out_path).name} (re-encoding, this may take a while)...")

    width, height = _video_size(video_path)
    duration = _media_duration(video_path)

    # The subtitles filter has painful escaping rules on Windows (drive colon,
    # backslashes, quotes), so work on a copy with a plain name in a temp dir.
    # Portrait videos get narrower lines so the text doesn't overflow the width.
    # Written as <name>.part.mp4 and renamed when complete: a video with the final
    # name is never half-written (cancel, crash, power cut).
    out_path = os.path.abspath(out_path)
    part = os.path.splitext(out_path)[0] + ".part.mp4"
    work = tempfile.mkdtemp(prefix="subburn_")
    try:
        line_width = PORTRAIT_LINE_WIDTH if height > width else LINE_WIDTH
        subtitles.write_srt(subtitles.read_srt(srt_path), os.path.join(work, "subs.srt"), width=line_width)
        cmd = ["ffmpeg", "-y", "-hide_banner", "-nostats",
               "-i", os.path.abspath(video_path),
               # The main picture (not cover art) and the first sound track, if any.
               "-map", "0:V:0", "-map", "0:a:0?",
               "-vf", f"subtitles=subs.srt:force_style='{_force_style(style, width, height)}'",
               "-c:v", "libx264", "-crf", "20", "-preset", "veryfast",   # ~3x faster than "medium", same size
               "-pix_fmt", "yuv420p",          # plays everywhere (phones, Instagram, browsers)
               "-c:a", "aac", "-b:a", "192k",
               "-movflags", "+faststart",
               "-progress", "pipe:1",
               part]
        proc = _start_tool(cmd, cwd=work, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        tail: list[str] = []
        ok = False
        try:
            for line in proc.stdout:
                _check_cancel(cancel)
                line = line.strip()
                # ffmpeg reports both keys in microseconds despite the name.
                if line.startswith(("out_time_us=", "out_time_ms=")) and duration:
                    try:
                        progress(min(int(line.split("=", 1)[1]) / 1_000_000 / duration, 1.0))
                    except ValueError:
                        pass
                elif "=" not in line and line:
                    tail = (tail + [line])[-20:]
            proc.wait()
            if proc.returncode != 0:
                raise RuntimeError("Could not create the subtitled video (ffmpeg failed).\n"
                                   + "\n".join(tail))
            os.replace(part, out_path)
            ok = True
        finally:
            if proc.poll() is None:           # cancelled or interrupted: stop ffmpeg now
                _kill_tree(proc)
            if not ok:                        # never leave a half-written video behind
                try:
                    os.remove(part)
                except OSError:
                    pass
    finally:
        _remove_dir(work)
    progress(1.0)
    log(f"Saved subtitled video: {out_path}")
    return str(out_path)


# --------------------------------------------------------------------------
# Main entry point
# --------------------------------------------------------------------------

# Output base path -> the video it belongs to (this session), so that lesson1\intro.mp4 and
# lesson2\intro.mp4 (or talk.mp4 and talk.mkv) don't overwrite each other's files.
_OUTPUT_OWNERS: dict[str, str] = {}


def _output_stem(video: Path, out_dir: Path) -> str:
    """Base name of a video's output files: its own name, or "name (2)", "name (3)"...
    when another video of this session already uses that name in out_dir."""
    me = os.path.normcase(os.path.abspath(video))
    n = 1
    while True:
        stem = video.stem if n == 1 else f"{video.stem} ({n})"
        key = os.path.normcase(os.path.abspath(out_dir / stem))
        if _OUTPUT_OWNERS.setdefault(key, me) == me:
            return stem
        n += 1


def _save_subtitles(write, cues: list[subtitles.Cue], path: Path, log: Callable[[str], None]) -> None:
    """Write an SRT/VTT file. An existing file with different content (maybe corrected
    in the editor) is kept as <name>.bak-YYYYmmdd-HHMMSS instead of being lost."""
    try:
        old = path.read_bytes() if path.is_file() else None
        write(cues, str(path), width=LINE_WIDTH)
        if old is not None and old != path.read_bytes():
            backup = path.with_name(f"{path.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
            backup.write_bytes(old)
            log(f"The previous {path.name} was kept as {backup.name}")
    except OSError as e:
        raise RuntimeError(f"Could not save the subtitles ({e.strerror or e}). "
                           f"Choose another output folder.\n{path}") from e


def process_video(video_path: str, target_langs: list[str] | str, source_lang: str | None = None,
                  model_size: str = DEFAULT_MODEL, translator: str = DEFAULT_TRANSLATOR,
                  burn: bool = False, burn_style: BurnStyle | None = None,
                  output_dir: str | None = None, glossary_path: str | None = None,
                  log: Callable[[str], None] = print,
                  progress: Callable[[float], None] = lambda p: None,
                  cancel: threading.Event | None = None, vtt: bool = False) -> dict:
    """Create original + translated subtitles for one video (optionally burned videos).

    Returns {"video", "detected_language", "original_srt",
             "translated_srts": {lang: path}, "burned_videos": {lang: path}}.
    """
    video = Path(video_path)
    if not video.is_file():
        raise FileNotFoundError(f"Video not found: {video.name} (was it moved or renamed?)")
    if isinstance(target_langs, str):
        target_langs = [target_langs]
    targets = [t for t in dict.fromkeys(_resolve_lang(t) for t in target_langs) if t]
    if not targets:
        raise ValueError("Choose at least one target language.")
    source = _resolve_lang(source_lang)
    out_dir = Path(output_dir) if output_dir else video.parent
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"Could not create the output folder {out_dir} ({e.strerror or e}).") from e
    stem = _output_stem(video, out_dir)
    gloss = glossary_mod.load_glossary(glossary_path)

    # 1. Speech recognition
    progress(0.0)
    tmp_dir = tempfile.mkdtemp(prefix="subtr_")
    try:
        _check_cancel(cancel)
        extract_audio(str(video), os.path.join(tmp_dir, "audio.wav"), log, cancel)
        progress(_P_AUDIO)
        segments, detected = transcribe(os.path.join(tmp_dir, "audio.wav"), source, model_size,
                                        gloss.whisper_prompt(), log,
                                        _scaled(progress, _P_AUDIO, _P_TRANSCRIBE), cancel)
    finally:
        _remove_dir(tmp_dir)
    if not segments:
        raise RuntimeError("No speech was found in this video (only silence, music or noise?).")

    # 2. Readable cues in the original language
    cues = subtitles.build_cues(segments, max_chars_per_line=LINE_WIDTH)
    for c in cues:  # glossary spelling, e.g. "Dilgem" -> "DİLGEM"
        c.text = gloss.fix_terms(c.text, source or detected)
    src_code = source or detected
    original_srt = out_dir / f"{stem}.{src_code}.srt"
    _save_subtitles(subtitles.write_srt, cues, original_srt, log)
    if vtt:
        _save_subtitles(subtitles.write_vtt, cues, original_srt.with_suffix(".vtt"), log)
    log(f"Transcription finished: {len(cues)} subtitles. Saved {original_srt.name}")

    # 3. Translation, one language at a time (cue timings stay the same)
    texts = [c.text.replace("\n", " ") for c in cues]
    translated_srts: dict[str, str] = {}
    step = (_P_TRANSLATE - _P_TRANSCRIBE) / len(targets)
    for n, lang in enumerate(targets):
        _check_cancel(cancel)
        path = out_dir / f"{stem}.{lang}.srt"
        if lang == src_code:
            translated_srts[lang] = str(original_srt)
            continue
        log(f"Translating {src_code} -> {lang}...")
        start = _P_TRANSCRIBE + n * step
        out_texts = translation.translate_texts(texts, src_code, lang, translator, gloss, log,
                                                _scaled(progress, start, start + step), cancel)
        out_cues = [subtitles.Cue(c.start, c.end, t) for c, t in zip(cues, out_texts)]
        _save_subtitles(subtitles.write_srt, out_cues, path, log)
        if vtt:
            _save_subtitles(subtitles.write_vtt, out_cues, path.with_suffix(".vtt"), log)
        translated_srts[lang] = str(path)
        log(f"Saved {path.name}")
    progress(_P_TRANSLATE)

    # 4. Optional burned-in videos
    burned: dict[str, str] = {}
    if burn:
        step = (1.0 - _P_TRANSLATE) / len(targets)
        for n, lang in enumerate(targets):
            _check_cancel(cancel)
            start = _P_TRANSLATE + n * step
            out = out_dir / f"{stem}.{lang}.subtitled.mp4"
            burned[lang] = burn_video(str(video), translated_srts[lang], str(out), burn_style,
                                      log, _scaled(progress, start, start + step), cancel)

    progress(1.0)
    log("Done.")
    return {
        "video": str(video),
        "detected_language": detected,
        "original_srt": str(original_srt),
        "translated_srts": translated_srts,
        "burned_videos": burned,
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate and translate subtitles for a video.")
    parser.add_argument("video")
    parser.add_argument("--to", nargs="+", required=True, help="target language(s), e.g. tr en")
    parser.add_argument("--from", dest="src", default=None, help="source language (default: auto-detect)")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=MODEL_SIZES)
    parser.add_argument("--translator", default=DEFAULT_TRANSLATOR, choices=sorted(set(TRANSLATORS.values())))
    parser.add_argument("--glossary", default=None, help="glossary file (default: glossary.txt)")
    parser.add_argument("--out", default=None, help="output folder (default: video folder)")
    parser.add_argument("--vtt", action="store_true", help="also write WebVTT files")
    parser.add_argument("--burn", action="store_true", help="also burn subtitles into MP4s")
    parser.add_argument("--position", default="bottom", choices=["bottom", "top"])
    parser.add_argument("--size", default="auto", choices=["auto", "small", "medium", "large"])
    parser.add_argument("--box", action="store_true", help="background box behind subtitles")
    parser.add_argument("--font", default="Arial")
    args = parser.parse_args()
    # A redirected console may not be UTF-8: never crash on Turkish/Arabic/Chinese text.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    last = [-1]

    def _cli_progress(p: float) -> None:
        pct = int(p * 100)
        if pct != last[0] and pct % 5 == 0:
            last[0] = pct
            print(f"  [{pct:3d}%]", flush=True)

    try:
        res = process_video(args.video, args.to, args.src, args.model, args.translator,
                            args.burn, BurnStyle(args.position, args.size, args.box, args.font),
                            args.out, args.glossary, log=lambda m: print(m, flush=True),
                            progress=_cli_progress, vtt=args.vtt)
        for k, v in res.items():
            print(f"{k}: {v}")
    except Cancelled:
        print("Cancelled.")
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
