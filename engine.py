"""Subtitle Translator engine: video -> speech recognition -> subtitles -> translation -> burn.

Orchestrates the other modules (see docs/ARCHITECTURE.md):
  subtitles.py   cue building, wrapping, SRT/VTT files
  translation.py translators (NLLB offline, Google online) and glossary enforcement
  glossary.py    the user's glossary of names and terms
  cuda_setup.py  making the pip-installed NVIDIA DLLs loadable
"""

from __future__ import annotations

import gc
import hashlib
import inspect
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

# Optional cleanup for very echoey / noisy recordings (extract_audio(clean=True)): cut rumble
# below 80 Hz and a mild FFT denoise. Kept gentle on purpose: Whisper copes well with normal
# room sound, strong denoising removes consonants, and volume levelling (dynaudnorm) lost
# words in a test on a real training recording (5 min, Whisper "small").
CLEAN_AUDIO_FILTER = "highpass=f=80,afftdn=nr=10:nf=-40"


def extract_audio(video_path: str, wav_path: str, log: Callable[[str], None],
                  cancel: threading.Event | None = None, clean: bool = False) -> None:
    if not _audio_streams(video_path):
        raise RuntimeError("This video has no sound track, so there is no speech to subtitle.")
    log("Extracting audio with ffmpeg (with noise and echo reduction)..." if clean
        else "Extracting audio with ffmpeg...")
    cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
           "-i", video_path, "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
           *(["-af", CLEAN_AUDIO_FILTER] if clean else []), "-f", "wav", wav_path]
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


def free_speech_model(log: Callable[[str], None] | None = None, device: str | None = "cuda") -> int:
    """Release the cached Whisper model(s) on `device` (None: all) and return how many.
    CTranslate2 frees the GPU memory when the model object is deleted; the next
    transcription simply loads the model again."""
    keys = [k for k in _MODEL_CACHE if device is None or k[1] == device]
    for k in keys:
        model = _MODEL_CACHE.pop(k)
        try:
            model.model.unload_model()   # frees the memory now, not at garbage collection
        except Exception:  # noqa: BLE001
            pass
        del model
    if keys:
        gc.collect()
        if log:
            log("Freed the speech recognition model from the GPU memory "
                "(room for the large translation model)." if device == "cuda"
                else "Freed the speech recognition model from memory.")
    return len(keys)


# --------------------------------------------------------------------------
# Checkpoints: resume speech recognition after a crash or power cut
# --------------------------------------------------------------------------
# While Whisper runs, every segment is appended to a JSON-lines file in
# %LOCALAPPDATA%\SubtitleTranslator\checkpoints (never next to the video). Lines:
#   {"v": 1, "language": "tr"}        header, written once the language is known
#   {"seg": {start, end, text, words}} a recognised segment
#   {"pos": 123.4}                     a skipped (hallucinated) segment: processed up to here
#   {"complete": true}                 speech recognition finished
# The next run of the same file (same size/date, model, language, cleanup) skips the
# audio up to the last position. The file is deleted when the video is finished.

CHECKPOINT_DIR = Path(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir()) / "SubtitleTranslator" / "checkpoints"
_CHECKPOINT_MAX_AGE = 30 * 86400   # older checkpoints (videos never finished) are removed


class _Checkpoint:
    def __init__(self, path: Path | None):
        self.path = path
        self.language: str | None = None
        self.segments: list[dict] = []
        self.position = 0.0
        self.complete = False
        if path is not None and path.is_file():
            self._load()

    def _load(self) -> None:
        good: list[str] = []
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            lines = []
        for line in lines:
            try:
                rec = json.loads(line)
                if "v" in rec:
                    if rec["v"] != 1:
                        break
                    self.language = rec.get("language")
                elif "seg" in rec and self.language:
                    seg = rec["seg"]
                    end = float(seg["end"])
                    if not isinstance(seg.get("text"), str) or not isinstance(seg.get("words"), list):
                        raise ValueError("bad segment")
                    self.segments.append(seg)
                    self.position = max(self.position, end)
                elif "pos" in rec and self.language:
                    self.position = max(self.position, float(rec["pos"]))
                elif rec.get("complete") and self.language:
                    self.complete = True
            except (ValueError, TypeError, KeyError, AttributeError):
                break                          # half-written last line (power cut) or damage
            good.append(line)
        if len(good) != len(lines):           # drop the damaged tail before appending to it
            self._rewrite(good)
        if not self.language:
            self.segments, self.position, self.complete = [], 0.0, False

    def _rewrite(self, lines: list[str]) -> None:
        try:
            self.path.write_text("".join(x + "\n" for x in lines), encoding="utf-8")
        except OSError:
            self.path = None

    def _append(self, rec: dict) -> None:
        if self.path is None:
            return
        try:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                os.fsync(f.fileno())           # survive a power cut
        except OSError:
            self.path = None                   # keep working without a checkpoint

    def start(self, language: str) -> None:
        if self.language is None:
            self.language = language
            self._append({"v": 1, "language": language})

    def add(self, seg: dict | None, position: float) -> None:
        if seg is not None:
            seg = {"start": round(seg["start"], 3), "end": round(seg["end"], 3), "text": seg["text"],
                   "words": [{"start": round(w["start"], 3), "end": round(w["end"], 3), "word": w["word"]}
                             for w in seg["words"]]}
            self.segments.append(seg)
            self._append({"seg": seg})
        else:
            self._append({"pos": round(position, 3)})
        self.position = max(self.position, position)

    def finish(self) -> None:
        self.complete = True
        self._append({"complete": True})

    def remove(self) -> None:
        if self.path is not None:
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass


def _checkpoint_path(video: Path, model_size: str, language: str | None, clean: bool,
                     log: Callable[[str], None]) -> Path | None:
    """Checkpoint file of this video + settings; None if the folder can't be used."""
    try:
        st = video.stat()
        key = "|".join([os.path.normcase(os.path.abspath(video)), str(st.st_size), str(st.st_mtime_ns),
                        model_size, language or "auto", "clean" if clean else "plain"])
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        now = time.time()
        for old in CHECKPOINT_DIR.glob("*.jsonl"):
            if now - old.stat().st_mtime > _CHECKPOINT_MAX_AGE:
                old.unlink(missing_ok=True)
        return CHECKPOINT_DIR / (hashlib.sha1(key.encode("utf-8")).hexdigest()[:20] + ".jsonl")
    except OSError as e:
        log(f"Could not save the progress of speech recognition ({e.strerror or e}); "
            "an interrupted run would start again from the beginning.")
        return None


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


_SAMPLE_RATE = 16000   # extract_audio's WAV format


def _run_transcription(model, wav_path, source_lang, prompt, log, progress, cancel, checkpoint=None):
    """Run Whisper, continuing after checkpoint.position (if any). Returns (segments, language)."""
    ckpt = checkpoint or _Checkpoint(None)
    offset = ckpt.position
    audio = wav_path
    total = 0.0
    if offset > 0:
        # Continue after the part already recognised: Whisper gets the rest of the audio,
        # its times are shifted back by `offset`.
        from faster_whisper import decode_audio

        samples = decode_audio(wav_path, sampling_rate=_SAMPLE_RATE)
        total = len(samples) / _SAMPLE_RATE
        audio = samples[int(offset * _SAMPLE_RATE):]
        if len(audio) < _SAMPLE_RATE // 2:            # less than half a second left
            progress(1.0)
            ckpt.finish()
            return list(ckpt.segments), ckpt.language or source_lang
    language = source_lang or ckpt.language       # keep the language detected by the first run
    segments_iter, info = model.transcribe(
        audio,
        language=language,
        vad_filter=True,
        beam_size=5,
        word_timestamps=True,               # needed for well-timed cues
        initial_prompt=prompt or None,      # glossary names help recognition
        condition_on_previous_text=False,   # avoids repetition loops on long recordings
    )
    if language is None:
        log(f"Detected language: {info.language} (probability {info.language_probability:.2f})")
        if info.language_probability < 0.6:
            log("  Not sure about the spoken language. If the subtitles look wrong, choose the "
                "spoken language instead of Auto-detect.")
    ckpt.start(info.language)

    duration = total or (info.duration or 0.0)
    segments = list(ckpt.segments)
    for seg in segments_iter:
        _check_cancel(cancel)
        start, end = seg.start + offset, seg.end + offset
        text = " ".join(seg.text.split())
        reason = _hallucination(seg) if text else None
        kept = None
        if reason:
            log(f"  Skipped {reason} at {_clock(start)} (not speech?): {text[:60]}")
        elif segments and text == segments[-1]["text"] and len(text) > 15 and \
                start - segments[-1]["end"] < 2:
            log(f"  Skipped a repeated line at {_clock(start)}: {text[:60]}")
        elif text:
            words = [{"start": w.start + offset, "end": w.end + offset, "word": w.word}
                     for w in (seg.words or [])]
            kept = {"start": start, "end": end, "text": text, "words": words}
            segments.append(kept)
        ckpt.add(kept, end)
        if duration > 0:
            progress(min(end / duration, 1.0))
    ckpt.finish()
    progress(1.0)
    return segments, info.language


def transcribe(wav_path: str, source_lang: str | None, model_size: str, prompt: str,
               log: Callable[[str], None], progress: Callable[[float], None],
               cancel: threading.Event | None, checkpoint: "_Checkpoint | None" = None):
    """Transcribe on the GPU if possible, otherwise on CPU. Returns (segments, language).
    With a checkpoint, segments are saved as they come and an earlier run is continued."""
    ckpt = checkpoint or _Checkpoint(None)
    cuda_setup.prepare_cuda_dlls(log)
    _model_files(model_size, log)   # a failed download must not look like a GPU problem
    if cuda_setup.cuda_usable(log):
        try:
            model = _load_model(model_size, "cuda", log)
            log("Transcribing on GPU...")
            return _run_transcription(model, wav_path, source_lang, prompt, log, progress, cancel, ckpt)
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"GPU transcription failed ({type(e).__name__}: {_one_line(e)}). Falling back to CPU.")
            _MODEL_CACHE.pop((model_size, "cuda"), None)
            gc.collect()
            # The CPU continues where the GPU stopped (the checkpoint has what was done).
    else:
        log("Using CPU (slower).")

    try:
        model = _load_model(model_size, "cpu", log)
    except Exception as e:  # noqa: BLE001
        raise RuntimeError(f"Could not load the speech recognition model ({type(e).__name__}: {_one_line(e)})") from e
    log("Transcribing on CPU...")
    return _run_transcription(model, wav_path, source_lang, prompt, log, progress, cancel, ckpt)


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


def _translate_groups(texts: list[str], src: str, lang: str, translator: str, gloss, log,
                      progress, cancel) -> list[tuple[list[int], str]]:
    """Translations of whole sentences: [(cue indices, translated sentence)]."""
    if "return_groups" in inspect.signature(translation.translate_texts).parameters:
        return translation.translate_texts(texts, src, lang, translator, gloss, log, progress, cancel,
                                           return_groups=True)
    # Older translation.py: one text per cue; join them back into their sentences.
    out = translation.translate_texts(texts, src, lang, translator, gloss, log, progress, cancel)
    return [(g, subtitles._clean("\n".join(out[i] for i in g)))
            for g in translation._sentence_groups(texts)]


def _retimed_cues(cues: list[subtitles.Cue], groups: list[tuple[list[int], str]]) -> list[subtitles.Cue]:
    """Translated cues laid out per sentence: each translation spans its sentence's
    original cues (first start to last end) and is split into readable subtitles."""
    items = [([(cues[i].start, cues[i].end) for i in idx], text)
             for idx, text in sorted(groups, key=lambda g: min(g[0]) if g[0] else 0)
             if idx and text and text.strip()]
    return subtitles.cues_for_texts(items, max_chars_per_line=LINE_WIDTH)


def _export_transcripts(cues: list[subtitles.Cue], srt: Path, lang: str, title: str,
                        formats: tuple[str, ...], log: Callable[[str], None]) -> list[str]:
    """<stem>.<lang>.transcript.<fmt> next to the SRT; a failure is logged, not fatal."""
    import transcript

    paths = []
    for fmt in formats:
        path = srt.with_name(f"{srt.stem}.transcript.{fmt}")
        try:
            transcript.export_transcript(cues, str(path), title, lang, fmt=fmt)
        except Exception as e:  # noqa: BLE001  (file open in Word, python-docx missing, ...)
            log(f"Could not save the transcript {path.name} ({_one_line(e)}).")
            continue
        paths.append(str(path))
        log(f"Saved {path.name}")
    return paths


def process_video(video_path: str, target_langs: list[str] | str, source_lang: str | None = None,
                  model_size: str = DEFAULT_MODEL, translator: str = DEFAULT_TRANSLATOR,
                  burn: bool = False, burn_style: BurnStyle | None = None,
                  output_dir: str | None = None, glossary_path: str | None = None,
                  log: Callable[[str], None] = print,
                  progress: Callable[[float], None] = lambda p: None,
                  cancel: threading.Event | None = None, vtt: bool = False,
                  retime_translation: bool = True, resume: bool = True, clean_audio: bool = False,
                  export_formats: tuple[str, ...] = (),
                  stage: Callable[[str, dict], None] | None = None) -> dict:
    """Create original + translated subtitles for one video (optionally burned videos).

    retime_translation: translated subtitles follow whole sentences (their number may differ
        from the original's); False keeps the original cue timings, one translation per cue.
    resume: continue an interrupted speech recognition of the same video and settings.
    clean_audio: ffmpeg noise/echo reduction before speech recognition (very poor recordings).
    export_formats: also write readable transcripts, e.g. ("docx", "txt", "md").
    stage(name, info): called when a stage starts ("audio", "transcribe", "translate", "burn")
        with {"start", "end"} (its share of the 0..1 progress), "audio_duration",
        "resume_from" (seconds already recognised) and "lang" (translate/burn).

    Returns {"video", "detected_language", "original_srt", "translated_srts": {lang: path},
             "burned_videos": {lang: path}, "transcripts": {lang: [paths]},
             "audio_duration": seconds, "resumed_from": seconds,
             "timings": {"audio": s, "transcribe": s, "translate": {lang: s}, "burn": {lang: s}}}.
    """
    video = Path(video_path)
    if not video.is_file():
        raise FileNotFoundError(f"Video not found: {video.name} (was it moved or renamed?)")
    if isinstance(target_langs, str):
        target_langs = [target_langs]
    targets = [t for t in dict.fromkeys(_resolve_lang(t) for t in target_langs) if t]
    if not targets:
        raise ValueError("Choose at least one target language.")
    formats = tuple(dict.fromkeys(f.lower().lstrip(".") for f in export_formats or ()))
    bad = [f for f in formats if f not in ("docx", "txt", "md")]
    if bad:
        raise ValueError(f"Unknown transcript format: {bad[0]}")
    source = _resolve_lang(source_lang)
    out_dir = Path(output_dir) if output_dir else video.parent
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"Could not create the output folder {out_dir} ({e.strerror or e}).") from e
    stem = _output_stem(video, out_dir)
    gloss = glossary_mod.load_glossary(glossary_path)
    timings: dict = {"audio": 0.0, "transcribe": 0.0, "translate": {}, "burn": {}}

    # 1. Speech recognition (continuing an interrupted run of the same video if possible)
    progress(0.0)
    _check_cancel(cancel)
    ckpt = _Checkpoint(_checkpoint_path(video, model_size, source, clean_audio, log) if resume else None)
    resumed_from = ckpt.position
    duration = _media_duration(str(video))

    def _stage(name: str, start: float, end: float, **extra) -> None:
        if stage is not None:
            stage(name, {"start": start, "end": end, "audio_duration": duration,
                         "resume_from": resumed_from, **extra})

    if ckpt.complete:
        log("Speech recognition was already finished by the previous (interrupted) run; using its result.")
        segments, detected = list(ckpt.segments), ckpt.language
    else:
        if duration > 0:
            log(f"Audio length: {_clock(duration)}.")
        if resumed_from > 0:
            log(f"Continuing from {_clock(resumed_from)} (previous run was interrupted).")
        tmp_dir = tempfile.mkdtemp(prefix="subtr_")
        try:
            _stage("audio", 0.0, _P_AUDIO)
            t0 = time.monotonic()
            extract_audio(str(video), os.path.join(tmp_dir, "audio.wav"), log, cancel, clean=clean_audio)
            timings["audio"] = round(time.monotonic() - t0, 1)
            progress(_P_AUDIO)
            _stage("transcribe", _P_AUDIO, _P_TRANSCRIBE)
            t0 = time.monotonic()
            segments, detected = transcribe(os.path.join(tmp_dir, "audio.wav"), source, model_size,
                                            gloss.whisper_prompt(), log,
                                            _scaled(progress, _P_AUDIO, _P_TRANSCRIBE), cancel, ckpt)
            timings["transcribe"] = round(time.monotonic() - t0, 1)
        finally:
            _remove_dir(tmp_dir)
    if not segments:
        ckpt.remove()
        raise RuntimeError("No speech was found in this video (only silence, music or noise?).")
    progress(_P_TRANSCRIBE)

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
    transcripts: dict[str, list[str]] = {}
    if formats:
        transcripts[src_code] = _export_transcripts(cues, original_srt, src_code, video.stem, formats, log)

    # The large offline translator (3.3 GB) only fits on a 4 GB card without Whisper.
    if translator == "nllb_large" and any(code != src_code for code in targets) \
            and any(dev == "cuda" for _, dev in _MODEL_CACHE):
        free_speech_model(log)
        if hasattr(translation, "free_gpu_models"):
            translation.free_gpu_models()

    # 3. Translation, one language at a time
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
        _stage("translate", start, start + step, lang=lang)
        t0 = time.monotonic()
        prog = _scaled(progress, start, start + step)
        if retime_translation:
            out_cues = _retimed_cues(cues, _translate_groups(texts, src_code, lang, translator, gloss,
                                                             log, prog, cancel))
        else:
            out_texts = translation.translate_texts(texts, src_code, lang, translator, gloss, log, prog, cancel)
            out_cues = [subtitles.Cue(c.start, c.end, t) for c, t in zip(cues, out_texts)]
        timings["translate"][lang] = round(time.monotonic() - t0, 1)
        _save_subtitles(subtitles.write_srt, out_cues, path, log)
        if vtt:
            _save_subtitles(subtitles.write_vtt, out_cues, path.with_suffix(".vtt"), log)
        translated_srts[lang] = str(path)
        log(f"Saved {path.name}")
        if formats:
            transcripts[lang] = _export_transcripts(out_cues, path, lang, video.stem, formats, log)
    progress(_P_TRANSLATE)

    # 4. Optional burned-in videos
    burned: dict[str, str] = {}
    if burn:
        step = (1.0 - _P_TRANSLATE) / len(targets)
        for n, lang in enumerate(targets):
            _check_cancel(cancel)
            start = _P_TRANSLATE + n * step
            _stage("burn", start, start + step, lang=lang)
            t0 = time.monotonic()
            out = out_dir / f"{stem}.{lang}.subtitled.mp4"
            burned[lang] = burn_video(str(video), translated_srts[lang], str(out), burn_style,
                                      log, _scaled(progress, start, start + step), cancel)
            timings["burn"][lang] = round(time.monotonic() - t0, 1)

    ckpt.remove()   # finished: running the same video again starts from scratch
    progress(1.0)
    log("Done.")
    return {
        "video": str(video),
        "detected_language": detected,
        "original_srt": str(original_srt),
        "translated_srts": translated_srts,
        "burned_videos": burned,
        "transcripts": transcripts,
        "audio_duration": duration,
        "resumed_from": resumed_from,
        "timings": timings,
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
    parser.add_argument("--translator", default=DEFAULT_TRANSLATOR, choices=sorted(getattr(translation, "_TRANSLATOR_IDS", set(TRANSLATORS.values()))))
    parser.add_argument("--glossary", default=None, help="glossary file (default: glossary.txt)")
    parser.add_argument("--out", default=None, help="output folder (default: video folder)")
    parser.add_argument("--vtt", action="store_true", help="also write WebVTT files")
    parser.add_argument("--burn", action="store_true", help="also burn subtitles into MP4s")
    parser.add_argument("--position", default="bottom", choices=["bottom", "top"])
    parser.add_argument("--size", default="auto", choices=["auto", "small", "medium", "large"])
    parser.add_argument("--box", action="store_true", help="background box behind subtitles")
    parser.add_argument("--font", default="Arial")
    parser.add_argument("--transcript", nargs="+", default=[], choices=["docx", "txt", "md"],
                        help="also write readable transcripts in these formats")
    parser.add_argument("--clean-audio", action="store_true", help="noise/echo reduction before recognition")
    parser.add_argument("--keep-timing", action="store_true",
                        help="translated subtitles keep the original cue timings (no sentence re-timing)")
    parser.add_argument("--no-resume", action="store_true", help="don't continue an interrupted run")
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
                            progress=_cli_progress, vtt=args.vtt,
                            retime_translation=not args.keep_timing, resume=not args.no_resume,
                            clean_audio=args.clean_audio, export_formats=tuple(args.transcript))
        for k, v in res.items():
            print(f"{k}: {v}")
    except Cancelled:
        print("Cancelled.")
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
