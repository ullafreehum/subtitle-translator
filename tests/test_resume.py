r"""Resume after a crash: cancel speech recognition midway, run again, it continues (CPU, Whisper "tiny"):

    .venv\Scripts\python.exe tests\test_resume.py [--model tiny]

A ~2.5-minute spoken test video is made with Windows text-to-speech (tests/sample_media.py).
Checkpoints go to a temporary folder, not %LOCALAPPDATA%.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"   # CPU only, before ctranslate2 is imported

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import engine  # noqa: E402
import sample_media  # noqa: E402
from subtitles import read_srt  # noqa: E402

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ok    " if cond else "  FAIL  ") + msg)
    if not cond:
        failures.append(msg)


def make_long_video(d: str, repeats: int = 4) -> str | None:
    wav = os.path.join(d, "speech.wav")
    if not sample_media.speak_to_wav(" ".join([sample_media.SCRIPT] * repeats), wav):
        return None
    video = os.path.join(d, "long talk.mp4")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=0x1e3a8a:s=320x180:r=10",
                    "-i", wav, "-shortest", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", video], check=True)
    return video


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="tiny")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="test_resume_") as d:
        engine.CHECKPOINT_DIR = Path(d, "checkpoints")
        video = make_long_video(d)
        if not video:
            print("Skipped: Windows text-to-speech is not available.")
            return 0
        out = os.path.join(d, "out")
        duration = engine._media_duration(video)
        print(f"== test video: {duration:.0f} s")
        opts = dict(source_lang="en", model_size=args.model, output_dir=out)

        # 1. Cancel when about 40 % of the audio is recognised (like a crash or power cut).
        cancel = threading.Event()

        def progress(p: float) -> None:
            if p >= engine._P_AUDIO + 0.4 * (engine._P_TRANSCRIBE - engine._P_AUDIO):
                cancel.set()

        try:
            engine.process_video(video, ["en"], log=lambda m: None, progress=progress, cancel=cancel, **opts)
            check(False, "first run should be cancelled")
        except engine.Cancelled:
            pass
        files = list(engine.CHECKPOINT_DIR.glob("*.jsonl"))
        ck = engine._Checkpoint(files[0]) if files else None
        check(ck is not None and 0.3 * duration < ck.position < 0.8 * duration and ck.segments and not ck.complete,
              f"checkpoint after cancel: {ck and round(ck.position, 1)} s, {ck and len(ck.segments)} segments")

        # 2. Run again: continues from the checkpoint.
        lines: list[str] = []
        t0 = time.monotonic()
        res = engine.process_video(video, ["en"], log=lines.append, **opts)
        resumed_secs = time.monotonic() - t0
        cont = [x for x in lines if x.startswith("Continuing from ")]
        check(bool(cont) and res["resumed_from"] == ck.position, f"log: {cont}")
        check(not list(engine.CHECKPOINT_DIR.glob("*.jsonl")), "checkpoint deleted after the video finished")
        resumed = read_srt(res["original_srt"])

        # 3. The same without resuming, for comparison.
        t0 = time.monotonic()
        res = engine.process_video(video, ["en"], log=lambda m: None, resume=False, **opts)
        full_secs = time.monotonic() - t0
        full = read_srt(res["original_srt"])
        words_r = sum(len(c.text.split()) for c in resumed)
        words_f = sum(len(c.text.split()) for c in full)
        print(f"  resumed: {len(resumed)} cues / {words_r} words in {resumed_secs:.0f} s; "
              f"full: {len(full)} cues / {words_f} words in {full_secs:.0f} s")
        check(resumed[0].start < 3 and resumed[-1].end > duration - 10, "resumed result covers the whole video")
        check(abs(words_r - words_f) <= 0.05 * words_f, "about the same words as an uninterrupted run")
        check(all(b.start >= a.end for a, b in zip(resumed, resumed[1:])), "no overlaps at the seam")
        seam = [c for c in resumed if abs(c.start - ck.position) < 15]
        print("  around the seam: " + " | ".join(" ".join(c.text.split()) for c in seam))
    print(f"\n{'ALL OK' if not failures else f'{len(failures)} FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
