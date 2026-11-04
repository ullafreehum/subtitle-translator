"""Stand-in for engine.py (same public API as docs/ARCHITECTURE.md) for GUI tests.

process_video writes small generated SRTs instead of transcribing (and logs the same
step messages as the real engine, so the status bar can be checked); burn_video just
simulates progress and writes an empty file. Install with: sys.modules["engine"] = fake_engine
"""

import os
import sys
import threading
import time
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import subtitles  # noqa: E402

LANGUAGES = {"English": "en", "Turkish": "tr", "German": "de", "French": "fr", "Arabic": "ar"}
MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3-turbo"]
DEFAULT_MODEL = "large-v3-turbo"
TRANSLATORS = {"NLLB (offline, on this PC)": "nllb", "Google (online)": "online"}
DEFAULT_TRANSLATOR = "nllb"
LARGE_INSTALLED = False    # available_translators() lists "nllb_large" only when True
AUDIO_DURATION = 12.0      # "audio_duration" of the result (seconds)

STEP_DELAY = 0.02          # seconds per progress step
FAIL_NAMES = set()         # video basenames that should raise
SAMPLE_TEXTS = ["Merhaba, DİLGEM eğitimine hoş geldiniz.", "Bugün oyun terapisini konuşacağız.",
                "Çocuklar oyunla kendilerini ifade eder.", "Teşekkürler, görüşmek üzere!"]


class Cancelled(Exception):
    pass


@dataclass
class BurnStyle:
    position: str = "bottom"
    font_size: str = "auto"
    box: bool = False
    font: str = "Arial"


calls: list = []           # recorded (function, args) for assertions


def available_translators() -> dict:
    """Like translation.available_translators(): the large model only when installed."""
    names = dict(TRANSLATORS)
    if LARGE_INSTALLED:
        names = {"NLLB (offline, on this PC)": "nllb",
                 "Offline – NLLB large model (best quality, slower)": "nllb_large",
                 "Google (online)": "online"}
    return names


def _steps(progress, cancel, start=0.0, end=1.0, n=10):
    for i in range(n + 1):
        if cancel is not None and cancel.is_set():
            raise Cancelled("Cancelled by user.")
        progress(start + (end - start) * i / n)
        time.sleep(STEP_DELAY)


def _write_sample(path: str, lang: str) -> None:
    cues = [subtitles.Cue(i * 3.0, i * 3.0 + 2.5, f"[{lang}] {t}") for i, t in enumerate(SAMPLE_TEXTS)]
    subtitles.write_srt(cues, path)


def process_video(video_path, target_langs, source_lang=None, model_size=DEFAULT_MODEL,
                  translator=DEFAULT_TRANSLATOR, burn=False, burn_style=None, output_dir=None,
                  glossary_path=None, log=print, progress=lambda p: None,
                  cancel: threading.Event | None = None, retime_translation: bool = True,
                  clean_audio: bool = False, export_formats: tuple = ()) -> dict:
    calls.append(("process_video", video_path, list(target_langs), dict(
        source_lang=source_lang, model_size=model_size, translator=translator, burn=burn,
        burn_style=burn_style, output_dir=output_dir, retime_translation=retime_translation,
        clean_audio=clean_audio, export_formats=tuple(export_formats))))
    if not os.path.isfile(video_path):
        raise FileNotFoundError(f"Video not found: {os.path.basename(video_path)} "
                                "(was it moved or renamed?)")
    if os.path.basename(video_path) in FAIL_NAMES:
        raise RuntimeError("Simulated failure\nsecond line")
    folder = output_dir or os.path.dirname(video_path)
    os.makedirs(folder, exist_ok=True)
    stem = os.path.splitext(os.path.basename(video_path))[0]
    source = source_lang or "en"

    # Same log lines as the real engine (the status line follows them).
    log("Extracting audio with ffmpeg (with noise and echo reduction)..." if clean_audio
        else "Extracting audio with ffmpeg...")
    log(f"Loading speech recognition model '{model_size}' on CPU...")
    log("Transcribing on CPU...")
    _steps(progress, cancel, 0.0, 0.6)
    original = os.path.join(folder, f"{stem}.{source}.srt")
    _write_sample(original, source)
    srts, videos = {}, {}
    for lang in target_langs:
        if lang == source:
            srts[lang] = original
            continue
        log(f"Translating {source} -> {lang}...")
        _steps(progress, cancel, 0.6, 0.85, n=4)
        srts[lang] = os.path.join(folder, f"{stem}.{lang}.srt")
        _write_sample(srts[lang], lang)
    if burn:
        for lang in target_langs:
            log(f"Burning subtitles into {stem}.{lang}.subtitled.mp4 (re-encoding)...")
            videos[lang] = burn_video(video_path, srts[lang],
                                      os.path.join(folder, f"{stem}.{lang}.subtitled.mp4"),
                                      burn_style, log, lambda p: None, cancel)
    transcripts = {}
    for lang in (dict.fromkeys([source] + list(target_langs)) if export_formats else ()):
        transcripts[lang] = []
        for fmt in export_formats:
            path = os.path.join(folder, f"{stem}.{lang}.transcript.{fmt}")   # as the engine
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(c.text for c in subtitles.read_srt(srts.get(lang, original))))
            transcripts[lang].append(path)
            log(f"Saved {os.path.basename(path)}")
    progress(1.0)
    log("Done.")
    return {"video": video_path, "detected_language": source, "original_srt": original,
            "translated_srts": srts, "burned_videos": videos, "transcripts": transcripts,
            "audio_duration": AUDIO_DURATION}


def burn_video(video_path, srt_path, out_path=None, style=None, log=print,
               progress=lambda p: None, cancel: threading.Event | None = None) -> str:
    calls.append(("burn_video", video_path, srt_path, style))
    log("[fake] burning")
    _steps(progress, cancel)
    if out_path is None:
        stem = os.path.splitext(os.path.basename(video_path))[0]
        lang = os.path.basename(srt_path).rsplit(".", 2)[-2]
        out_path = os.path.join(os.path.dirname(srt_path), f"{stem}.{lang}.subtitled.mp4")
    open(out_path, "wb").close()
    return out_path


# Stand-in for transcript.py (install with editor.get_transcript = lambda: fake_engine).
transcript_calls: list = []


def export_srt_transcript(srt_path, out_path, fmt, timestamps):
    transcript_calls.append((srt_path, out_path, fmt, timestamps))
    cues = subtitles.read_srt(srt_path)
    with open(out_path, "w", encoding="utf-8") as f:
        for c in cues:
            f.write((f"[{int(c.start) // 60:02d}:{int(c.start) % 60:02d}] " if timestamps else "")
                    + c.text.replace("\n", " ") + "\n")
    return out_path
