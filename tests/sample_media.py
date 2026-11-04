"""Made-up test media: a short training interview spoken by Windows text-to-speech.

No real recordings are used in the tests. make_sample_video() speaks SCRIPT with the
Windows speech synthesizer and puts it on a plain background with ffmpeg; the speech
recognition fixture (tests/fixtures/sample_segments.json) was made from the same audio:

    .venv\\Scripts\\python.exe tests\\sample_media.py --fixture
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = (
    "What did you think of the training with Dilgem? "
    "Overall, I think the training with Dilgem went very well. "
    "These courses can be hard to organize, because we ask a lot of the trainees, "
    "and of the families who volunteer their time with us. "
    "The trainees practiced the play routines with the children every afternoon, "
    "and the parents joined them on the last day. "
    "Would you come back to Istanbul to teach again? "
    "Yes, absolutely. "
    "It was a lovely experience, and the trainees asked excellent questions "
    "about the issues they see in their own clinics. "
    "Thank you."
)

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def speak_to_wav(text: str, wav_path: str) -> bool:
    """Windows text-to-speech into a WAV file. Returns False where it is not available."""
    if sys.platform != "win32":
        return False
    text_file = Path(wav_path).with_suffix(".txt")
    text_file.write_text(text, encoding="utf-8")
    ps = ("Add-Type -AssemblyName System.Speech; "
          "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
          f"$s.SetOutputToWaveFile('{wav_path}'); "
          f"$s.Speak([IO.File]::ReadAllText('{text_file}', [Text.Encoding]::UTF8)); $s.Dispose()")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True,
                       capture_output=True, timeout=120, creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return False
    return os.path.isfile(wav_path) and os.path.getsize(wav_path) > 1000


def make_sample_video(folder: str | None = None, speech: bool = True) -> str | None:
    """Create a short test video (spoken SCRIPT, or a tone) and return its path, or None."""
    folder = folder or tempfile.mkdtemp(prefix="sample_media_")
    video = os.path.join(folder, "sample training video.mp4")
    if os.path.isfile(video):
        return video
    wav = os.path.join(folder, "sample_speech.wav")
    if speech and speak_to_wav(SCRIPT, wav):
        audio = ["-i", wav]
    else:
        audio = ["-f", "lavfi", "-i", "sine=frequency=440:duration=8"]
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x1e3a8a:s=640x360:r=25",
           *audio, "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", video]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120, creationflags=_NO_WINDOW)
    except (OSError, subprocess.SubprocessError):
        return None
    return video if os.path.isfile(video) else None


def make_fixture(out_path: str) -> None:
    """Regenerate the speech-recognition fixture from the spoken SCRIPT (Whisper "base", CPU)."""
    from faster_whisper import WhisperModel

    folder = tempfile.mkdtemp(prefix="sample_fixture_")
    wav = os.path.join(folder, "speech.wav")
    if not speak_to_wav(SCRIPT, wav):
        raise SystemExit("Windows text-to-speech is not available.")
    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(wav, language="en", word_timestamps=True, vad_filter=True)
    data = [{"start": round(s.start, 3), "end": round(s.end, 3), "text": s.text,
             "words": [{"start": round(w.start, 3), "end": round(w.end, 3), "word": w.word}
                       for w in (s.words or [])]} for s in segments]
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    print(f"{len(data)} segments written to {out_path}")


if __name__ == "__main__":
    if "--fixture" in sys.argv:
        make_fixture(str(Path(__file__).resolve().parent / "fixtures" / "sample_segments.json"))
    else:
        print(make_sample_video())
