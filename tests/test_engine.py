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


FIXTURE = ROOT / "tests" / "fixtures" / "sample_segments.json"


def _fake_translate(texts, source, target, translator="nllb", glossary=None, log=print,
                    progress=lambda p: None, cancel=None, return_groups=False):
    """Stand-in for translation.translate_texts: a "translation" twice as long per sentence."""
    import translation

    groups = translation._sentence_groups(texts)
    full = [(g, " ".join(" ".join(texts[i].split()) for i in g) + " Bu çevirinin uzun bir eki, evet.")
            for g in groups]
    progress(1.0)
    if return_groups:
        return full
    out = list(texts)
    for g, t in full:
        for i in g:
            out[i] = f"[{target}] " + texts[i]
    return out


def _fake_translate_old(texts, source, target, translator="nllb", glossary=None, log=print,
                        progress=lambda p: None, cancel=None):
    """translate_texts before return_groups existed."""
    return [f"[{target}] " + t for t in texts]


def _no_overlaps(cues) -> bool:
    return all(b.start - a.end >= 0.08 - 1e-9 and a.end > a.start for a, b in zip(cues, cues[1:]))


def test_retime_and_exports(p: dict[str, str], out: str) -> None:
    """process_video without AI models: Whisper and the translator are stand-ins."""
    import docx
    import json
    import translation
    from subtitles import read_srt

    print("\n== re-timed translations, transcripts, stages (stand-in Whisper/translator)")
    segments = json.loads(FIXTURE.read_text(encoding="utf-8"))
    calls = []

    def fake_transcribe(wav, source, model_size, prompt, log, progress, cancel, checkpoint=None):
        calls.append(os.path.getsize(wav))
        progress(1.0)
        return [dict(s, text=" ".join(s["text"].split())) for s in segments], "en"

    real_transcribe, real_translate = engine.transcribe, translation.translate_texts
    engine.transcribe, translation.translate_texts = fake_transcribe, _fake_translate
    d = os.path.join(out, "retime")
    os.makedirs(d)
    stages: list[tuple[str, dict]] = []
    lines: list[str] = []
    try:
        res = engine.process_video(p["video.mp4"], ["tr", "en"], source_lang="en", output_dir=d,
                                   log=lines.append, burn=True, export_formats=("docx", "txt", "md"),
                                   stage=lambda name, info: stages.append((name, info)))
        orig, tr = read_srt(res["original_srt"]), read_srt(res["translated_srts"]["tr"])
        check(len(tr) != len(orig) and _no_overlaps(tr), f"re-timed: {len(orig)} -> {len(tr)} cues, no overlaps")
        check(all(len(c.text.split("\n")) <= 2 and all(len(x) <= 42 for x in c.text.split("\n")) for c in tr),
              "re-timed cues: 2 lines x 42")
        check(" ".join(" ".join(c.text.split()) for c in tr).count("Bu çevirinin uzun bir eki, evet.")
              == len(translation._sentence_groups([c.text for c in orig])), "every sentence's text kept")
        check(tr[0].start == orig[0].start and abs(tr[-1].end - orig[-1].end) < 6, "same overall span")
        check(set(res) >= {"transcripts", "audio_duration", "resumed_from", "timings"}, f"result keys: {sorted(res)}")
        check(abs(res["audio_duration"] - 3.0) < 0.2 and res["resumed_from"] == 0, f"duration {res['audio_duration']}")
        check(set(res["timings"]["translate"]) == {"tr"} and set(res["timings"]["burn"]) == {"tr", "en"},
              f"timings: {res['timings']}")
        check([s for s, _ in stages] == ["audio", "transcribe", "translate", "burn", "burn"],
              f"stages: {[s for s, _ in stages]}")
        check(stages[1][1]["start"] == engine._P_AUDIO and stages[1][1]["audio_duration"] > 2.5,
              f"stage info: {stages[1][1]}")
        check(any(x.startswith("Audio length: 0:03") for x in lines), "audio length logged")
        names = {lang: sorted(os.path.basename(x) for x in v) for lang, v in res["transcripts"].items()}
        stem = Path(p["video.mp4"]).stem
        check(names == {lang: [f"{stem}.{lang}.transcript.{f}" for f in ("docx", "md", "txt")]
                        for lang in ("en", "tr")}, f"transcripts: {names}")
        doc = docx.Document(os.path.join(d, f"{stem}.tr.transcript.docx"))
        paras = [x for x in doc.paragraphs if x.text]
        check(paras[0].style.name == "Title" and paras[0].text == stem, f"docx title: {paras[0].text!r}")
        check(paras[1].text.startswith("Dil: Türkçe · Tarih: "), f"docx header: {paras[1].text!r}")
        body = paras[2:]
        check(len(body) >= 2 and all(x.text.startswith("[00:00:") for x in body), f"docx paragraphs: {len(body)}")
        check(body[0].runs[0].font.color.rgb is not None, "docx timestamp is grey")
        txt = Path(d, f"{stem}.en.transcript.txt").read_text(encoding="utf-8")
        check(txt.startswith(f"{stem}\n") and "Language: English · Date: " in txt and "[00:00:00] What did" in txt,
              f"txt: {txt[:80]!r}")
        check(os.path.isfile(res["burned_videos"]["tr"]), "burning a re-timed SRT works")

        # Old behaviour on request: the original timings, one translation per cue.
        res = engine.process_video(p["video.mp4"], ["tr"], source_lang="en", output_dir=d, log=lambda m: None,
                                   retime_translation=False)
        tr = read_srt(res["translated_srts"]["tr"])
        check([(c.start, c.end) for c in tr] == [(c.start, c.end) for c in orig], "retime_translation=False")
        # A translation.py without return_groups: groups are rebuilt from the per-cue texts.
        translation.translate_texts = _fake_translate_old
        res = engine.process_video(p["video.mp4"], ["tr"], source_lang="en", output_dir=d, log=lambda m: None)
        tr = read_srt(res["translated_srts"]["tr"])
        check(_no_overlaps(tr) and " ".join(c.text for c in tr).count("[tr]") == len(orig),
              "older translation.py still works")

        # The large translator: Whisper is released from the GPU first.
        translation.translate_texts = _fake_translate
        freed = []
        old_free = getattr(translation, "free_gpu_models", None)
        translation.free_gpu_models = lambda: freed.append(1)
        engine._MODEL_CACHE[("tiny", "cuda")] = object()
        lines.clear()
        engine.process_video(p["video.mp4"], ["tr"], source_lang="en", output_dir=d, log=lines.append,
                             translator="nllb_large")
        check(("tiny", "cuda") not in engine._MODEL_CACHE and freed and
              any(x.startswith("Freed the speech recognition model from the GPU") for x in lines),
              "nllb_large: Whisper and the small NLLB freed before translating")
        if old_free is None:
            del translation.free_gpu_models
        else:
            translation.free_gpu_models = old_free
        e = error_of(engine.process_video, p["video.mp4"], ["tr"], output_dir=d, log=lambda m: None,
                     export_formats=("pdf",))
        check(isinstance(e, ValueError) and "transcript format" in str(e), f"bad format: {e}")
    finally:
        engine.transcribe, translation.translate_texts = real_transcribe, real_translate


def test_checkpoint(p: dict[str, str], out: str) -> None:
    print("\n== checkpoints (resume after a crash)")
    import json

    path = Path(out, "ck.jsonl")
    ck = engine._Checkpoint(path)
    check(ck.position == 0 and not ck.segments and not path.exists(), "new checkpoint: empty, no file yet")
    ck.start("tr")
    ck.add({"start": 1.0, "end": 2.5, "text": "Merhaba.", "words": [{"start": 1.0, "end": 2.5, "word": " Merhaba."}]}, 2.5)
    ck.add(None, 4.0)   # skipped noise
    with open(path, "a", encoding="utf-8") as f:
        f.write('{"seg": {"start": 5.0, "en')           # power cut in the middle of a line
    ck = engine._Checkpoint(path)
    check(ck.language == "tr" and ck.position == 4.0 and len(ck.segments) == 1 and not ck.complete,
          f"reloaded after a damaged tail: {ck.language}, {ck.position}, {len(ck.segments)}")
    ck.add({"start": 4.5, "end": 6.0, "text": "Devam.", "words": []}, 6.0)
    ck.finish()
    ck = engine._Checkpoint(path)
    check(ck.complete and ck.position == 6.0 and [s["text"] for s in ck.segments] == ["Merhaba.", "Devam."],
          "damaged line dropped, appending continues, completion saved")
    ck.remove()
    check(not path.exists(), "removed")

    a = engine._checkpoint_path(Path(p["video.mp4"]), "tiny", "en", False, print)
    check(a is not None and a.parent == engine.CHECKPOINT_DIR, f"checkpoint folder: {a}")
    check(a != engine._checkpoint_path(Path(p["video.mp4"]), "base", "en", False, print)
          and a != engine._checkpoint_path(Path(p["video.mp4"]), "tiny", None, False, print)
          and a != engine._checkpoint_path(Path(p["video.mp4"]), "tiny", "en", True, print),
          "model, language and cleanup are part of the key")

    # A run interrupted after speech recognition: the next run uses the saved result.
    segments = json.loads(FIXTURE.read_text(encoding="utf-8"))
    ck = engine._Checkpoint(a)
    ck.start("en")
    for s in segments:
        ck.add({**s, "text": " ".join(s["text"].split())}, s["end"])
    ck.finish()
    real = engine.transcribe
    engine.transcribe = lambda *a, **k: (_ for _ in ()).throw(AssertionError("transcribe called"))
    lines: list[str] = []
    try:
        res = engine.process_video(p["video.mp4"], ["en"], source_lang="en", model_size="tiny",
                                   output_dir=os.path.join(out, "resume"), log=lines.append)
        check(res["resumed_from"] == segments[-1]["end"] and lines[0].startswith("Speech recognition was "
              "already finished"), f"complete checkpoint reused: {lines[:1]}")
        check(not a.exists(), "checkpoint deleted when the video is finished")
    finally:
        engine.transcribe = real


def test_clean_audio(p: dict[str, str], out: str) -> None:
    print("\n== audio cleanup filter")
    msgs: list[str] = []
    wav = os.path.join(out, "clean.wav")
    engine.extract_audio(p["video.mp4"], wav, msgs.append, clean=True)
    dur = engine._media_duration(wav)
    check(abs(dur - 3.0) < 0.2 and "noise and echo" in msgs[0], f"cleaned audio: {dur:.2f}s, {msgs}")
    check(probe(wav, "stream=sample_rate,channels") == ["16000,1"], "16 kHz mono")

    class Fake:
        class model:
            @staticmethod
            def unload_model():
                unloaded.append(1)
    unloaded: list[int] = []
    engine._MODEL_CACHE.update({("tiny", "cuda"): Fake(), ("tiny", "cpu"): Fake()})
    check(engine.free_speech_model() == 1 and list(engine._MODEL_CACHE) == [("tiny", "cpu")] and unloaded,
          "free_speech_model frees the GPU model only")
    check(engine.free_speech_model(device=None) == 1 and not engine._MODEL_CACHE, "device=None frees all")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="test_engine_") as d:
        out = os.path.join(d, "out")
        os.makedirs(out)
        engine.CHECKPOINT_DIR = Path(d, "checkpoints")   # not the user's %LOCALAPPDATA%
        p = make_inputs(d)
        test_retime_and_exports(p, out)
        test_checkpoint(p, out)
        test_clean_audio(p, out)
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
