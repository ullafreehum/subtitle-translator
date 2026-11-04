r"""Checks for engine.py that need only ffmpeg, no AI models (plain python, no pytest):

    .venv\Scripts\python.exe tests\test_engine.py

Small test videos are generated with ffmpeg in a temporary folder: user-friendly errors for
broken / silent inputs, burning the main picture (not the cover art), no half-written files
after a cancel or a failure.
"""

from __future__ import annotations

import glob
import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import engine  # noqa: E402
from subtitles import Cue, write_srt  # noqa: E402

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ok    " if cond else "  FAIL  ") + msg)
    if not cond:
        failures.append(msg)


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def probe(path: str, entries: str) -> list[str]:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", entries, "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout
    return [line.strip().strip(",") for line in out.splitlines() if line.strip()]


def first_line(exc: Exception) -> str:
    """What the GUI shows after "Failed: "."""
    return str(exc).strip().splitlines()[0]


def error_of(func, *args, **kwargs) -> Exception | None:
    try:
        func(*args, **kwargs)
    except Exception as e:  # noqa: BLE001
        return e
    return None


def make_inputs(d: str) -> dict[str, str]:
    p = {name: os.path.join(d, name) for name in
         ("video.mp4", "noaudio.mp4", "cover.png", "cover.mp4", "Öğrenci's [test] (1).mkv", "broken.mp4")}
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=3",
           "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
           "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", p["video.mp4"])
    ffmpeg("-i", p["video.mp4"], "-an", "-c", "copy", p["noaudio.mp4"])
    ffmpeg("-f", "lavfi", "-i", "color=red:size=640x480", "-frames:v", "1", p["cover.png"])
    # Like a downloaded video: the cover art is a second, larger video stream.
    ffmpeg("-i", p["video.mp4"], "-i", p["cover.png"], "-map", "0", "-map", "1", "-c", "copy",
           "-disposition:v:1", "attached_pic", p["cover.mp4"])
    ffmpeg("-i", p["video.mp4"], "-c", "copy", p["Öğrenci's [test] (1).mkv"])
    Path(p["broken.mp4"]).write_text("this is not a video", encoding="utf-8")
    return p


def test_input_errors(p: dict[str, str], out: str) -> None:
    print("\n== friendly errors for bad inputs")
    quiet = {"output_dir": out, "log": lambda m: None}
    cases = [("broken.mp4", "Cannot open this file as a video"),
             ("noaudio.mp4", "no sound track"),
             ("missing.mp4", "Video not found: missing.mp4")]
    for name, expected in cases:
        e = error_of(engine.process_video, os.path.join(os.path.dirname(p["video.mp4"]), name), ["en"], **quiet)
        line = first_line(e) if e else ""
        check(e is not None and expected in line and len(line) <= 80, f"{name}: {line!r}")
    e = error_of(engine.process_video, p["video.mp4"], [], **quiet)
    check(isinstance(e, ValueError) and "target language" in first_line(e), f"no targets: {e}")


def test_ffmpeg_missing(p: dict[str, str]) -> None:
    print("\n== ffmpeg not installed")
    old = os.environ["PATH"]
    os.environ["PATH"] = ""
    try:
        e = error_of(engine.extract_audio, p["video.mp4"], os.path.join(tempfile.gettempdir(), "x.wav"),
                     lambda m: None)
    finally:
        os.environ["PATH"] = old
    check(e is not None and "not found" in first_line(e) and "setup.bat" in first_line(e), f"{e}")


def test_burn(p: dict[str, str], out: str) -> None:
    print("\n== burning")
    srt = os.path.join(out, "cover.tr.srt")
    write_srt([Cue(0.2, 2.5, "Merhaba dünya, bu bir deneme.")], srt)
    res = engine.burn_video(p["cover.mp4"], srt, log=lambda m: None)
    check(res == os.path.join(out, "cover.tr.subtitled.mp4") and os.path.isfile(res), f"output name: {res}")
    streams = probe(res, "stream=codec_type,width,height")
    check(streams == ["video,320,240", "audio"], f"main picture + sound, no cover art: {streams}")

    res = engine.burn_video(p["noaudio.mp4"], srt, os.path.join(out, "noaudio.subtitled.mp4"), log=lambda m: None)
    check(probe(res, "stream=codec_type") == ["video"], "video without sound burns too")

    odd = os.path.join(out, "Öğrenci's [test] (1).tr.srt")
    write_srt([Cue(0.2, 2.5, "Test")], odd)
    res = engine.burn_video(p["Öğrenci's [test] (1).mkv"], odd, log=lambda m: None)
    check(os.path.isfile(res) and res.endswith("Öğrenci's [test] (1).tr.subtitled.mp4"), f"odd name, mkv: {res}")

    # A failing ffmpeg (here: unreadable input) leaves no partial video behind.
    target = os.path.join(out, "broken.subtitled.mp4")
    e = error_of(engine.burn_video, p["broken.mp4"], srt, target, log=lambda m: None)
    check(e is not None and "subtitled video" in first_line(e), f"burn failure message: {e and first_line(e)}")
    check(not os.path.exists(target), "no partial file after a failed burn")


def test_burn_details(p: dict[str, str], out: str) -> None:
    print("\n== burn details")
    rotated = os.path.join(out, "rotated.mp4")       # a phone video stored sideways
    ffmpeg("-display_rotation", "90", "-i", p["video.mp4"], "-c", "copy", rotated)
    check(engine._video_size(rotated) == (240, 320), f"rotation: {engine._video_size(rotated)}")
    check(engine._video_size(p["cover.mp4"]) == (320, 240), "size of the main picture, not the cover")
    style = engine._force_style(engine.BurnStyle(font="Bad', Font:\\Name"), 320, 240)
    check("FontName=Bad FontName," in style, f"font name sanitised: {style}")
    top = engine._force_style(engine.BurnStyle(position="top"), 1080, 1920)
    check("Alignment=6," in top and "Alignment=2," in engine._force_style(engine.BurnStyle(), 320, 240),
          f"top = SSA alignment 6 (8 drew the text middle-left): {top}")
    style = engine._force_style(engine.BurnStyle(font="':,"), 320, 240)
    check(style.startswith("FontName=Arial,"), f"empty font -> Arial: {style}")

    srt = os.path.join(out, "cover.tr.srt")
    res = engine.burn_video(p["video.mp4"], srt, os.path.join(out, "pix.subtitled.mp4"), log=lambda m: None)
    check(probe(res, "stream=pix_fmt") == ["yuv420p"], "yuv420p output")
    check(not glob.glob(os.path.join(out, "*.part.mp4")), "no .part.mp4 left after a burn")


def test_output_names(out: str) -> None:
    print("\n== output names and backups")
    a, b = Path(out, "lesson1", "intro.mp4"), Path(out, "lesson2", "intro.mp4")
    check(engine._output_stem(a, Path(out)) == "intro", "first video keeps its name")
    check(engine._output_stem(b, Path(out)) == "intro (2)", "same name from another folder -> (2)")
    check(engine._output_stem(Path(out, "lesson1", "intro.mkv"), Path(out)) == "intro (3)", "other container -> (3)")
    check(engine._output_stem(a, Path(out)) == "intro", "the same video again reuses its name")
    check(engine._output_stem(b, Path(out, "lesson2")) == "intro", "different output folder: no suffix")

    path = Path(out, "intro.tr.srt")
    msgs: list[str] = []
    engine._save_subtitles(write_srt, [Cue(0, 1, "Makine çevirisi")], path, msgs.append)
    engine._save_subtitles(write_srt, [Cue(0, 1, "Makine çevirisi")], path, msgs.append)
    check(not glob.glob(str(path) + ".bak-*") and not msgs, "identical content: no backup")
    path.write_text("1\n00:00:00,000 --> 00:00:01,000\nDüzeltilmiş metin\n", encoding="utf-8")  # edited
    engine._save_subtitles(write_srt, [Cue(0, 1, "Makine çevirisi")], path, msgs.append)
    backups = glob.glob(str(path) + ".bak-*")
    check(len(backups) == 1 and "Düzeltilmiş" in Path(backups[0]).read_text(encoding="utf-8"),
          f"edited SRT kept as backup: {[os.path.basename(x) for x in backups]} / {msgs}")


def test_hallucination_filter() -> None:
    print("\n== Whisper hallucinations")
    from types import SimpleNamespace as NS

    def seg(text: str, prob: float) -> NS:
        return NS(text=text, words=[NS(probability=prob) for _ in text.split()])

    # Real cases: a silent clip gave "Gülcan Özen" / "DİLGEM ." (echo of the glossary prompt).
    check(engine._hallucination(seg(" DİLGEM .", 0.02)) == "unclear sound", "prompt echo in silence")
    check(engine._hallucination(seg(" Altyazı M.K.", 0.9)) == "subtitle credit", "subtitle credit")
    check(engine._hallucination(seg(" Subtitles by the Amara.org community", 0.9)) == "subtitle credit",
          "Amara credit")
    check(engine._hallucination(seg(" Bugün çocuklarla oyun terapisi yaptık.", 0.9)) is None, "real speech kept")
    check(engine._hallucination(seg(" It's on udemy.com, so check that out.", 0.9)) is None, "web address kept")


def test_cancel(p: dict[str, str], out: str) -> None:
    print("\n== cancel")
    temp_before = set(glob.glob(os.path.join(tempfile.gettempdir(), "sub*_*")))
    srt = os.path.join(out, "cover.tr.srt")
    target = os.path.join(out, "cancelled.subtitled.mp4")
    cancel = threading.Event()
    seen = []

    def progress(x: float) -> None:     # cancel as soon as encoding has started
        seen.append(x)
        if x > 0:
            cancel.set()

    long_video = os.path.join(out, "long.mp4")
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=1280x720:rate=25:duration=60", "-c:v", "libx264",
           "-preset", "ultrafast", long_video)
    e = error_of(engine.burn_video, long_video, srt, target, log=lambda m: None, progress=progress, cancel=cancel)
    check(isinstance(e, engine.Cancelled), f"burn raises Cancelled: {e!r}")
    check(not os.path.exists(target), "no partial video after cancel")

    cancel = threading.Event()
    cancel.set()
    e = error_of(engine.process_video, p["video.mp4"], ["tr"], output_dir=out, log=lambda m: None, cancel=cancel)
    check(isinstance(e, engine.Cancelled), f"process_video raises Cancelled: {e!r}")
    leftovers = set(glob.glob(os.path.join(tempfile.gettempdir(), "sub*_*"))) - temp_before
    check(not leftovers, f"no temp folders left: {leftovers}")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="test_engine_") as d:
        out = os.path.join(d, "out")
        os.makedirs(out)
        p = make_inputs(d)
        test_input_errors(p, out)
        test_ffmpeg_missing(p)
        test_burn(p, out)
        test_burn_details(p, out)
        test_output_names(out)
        test_hallucination_filter()
        test_cancel(p, out)
    print(f"\n{'ALL OK' if not failures else f'{len(failures)} FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
