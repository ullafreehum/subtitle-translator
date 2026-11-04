r"""Checks for i18n_engine.py, the Turkish texts of the engine's messages (plain python, no pytest):

    .venv\Scripts\python.exe tests\test_i18n_engine.py               # patterns + error paths + real run
    .venv\Scripts\python.exe tests\test_i18n_engine.py --quick       # patterns only (no ffmpeg, no models)
    .venv\Scripts\python.exe tests\test_i18n_engine.py --video X.mp4 --out FOLDER

1. Every pattern has a sample English line (as the engine writes it) with its expected Turkish.
2. English mode and unknown lines are returned unchanged.
3. Error paths (missing, broken and silent videos): the first line of the error is Turkish.
4. A real short run on the CPU (Whisper "tiny", NLLB): how many log lines came out Turkish.
   The video is copied into the output folder first; the original is only read.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import string
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"   # CPU only, before ctranslate2 is imported

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import i18n  # noqa: E402
import i18n_engine  # noqa: E402

DEFAULT_VIDEO = ""  # empty: a made-up spoken test video is created (tests/sample_media.py)

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ok    " if cond else "  FAIL  ") + msg)
    if not cond:
        failures.append(msg)


# English line as the engine writes it -> expected Turkish.
SAMPLES: list[tuple[str, str]] = [
    ("Cancelled by user.", "Kullanıcı tarafından iptal edildi."),
    ("Done.", "Tamamlandı."),
    ("Video not found: lesson 1 (final).mp4 (was it moved or renamed?)",
     "Video bulunamadı: lesson 1 (final).mp4 (taşınmış ya da adı değiştirilmiş olabilir)."),
    ("Choose at least one target language.", "En az bir çeviri dili seçin."),
    (r"Could not create the output folder D:\Out (2)\subs (Access is denied).",
     r"Çıktı klasörü oluşturulamadı: D:\Out (2)\subs (Access is denied)."),
    ("FFmpeg is missing (ffprobe not found). Run setup.bat again.",
     "FFmpeg bulunamadı (ffprobe yok). setup.bat dosyasını yeniden çalıştırın."),
    ("If it still fails, restart Windows and try once more.",
     "Sorun sürerse Windows'u yeniden başlatıp bir kez daha deneyin."),
    ("Cannot open this file as a video (damaged, incomplete or not a video).",
     "Bu dosya video olarak açılamadı (bozuk, eksik ya da video dosyası değil)."),
    ("This video has no sound track, so there is no speech to subtitle.",
     "Bu videoda ses yok; altyazıya dökülecek bir konuşma bulunmuyor."),
    ("Extracting audio with ffmpeg...", "Videonun sesi alınıyor (ffmpeg)..."),
    ("Could not read the sound of this video (ffmpeg failed).",
     "Bu videonun sesi okunamadı (ffmpeg hata verdi)."),
    ("Downloading the speech recognition model 'tiny' (75 MB, only once). This can take several minutes...",
     "Konuşma tanıma modeli 'tiny' indiriliyor (75 MB, yalnızca ilk seferde). Bu birkaç dakika sürebilir..."),
    ("Downloading the offline translation model (about 1.3 GB, only once). This can take several minutes...",
     "Çevrimdışı çeviri modeli indiriliyor (yaklaşık 1.3 GB, yalnızca ilk seferde). "
     "Bu birkaç dakika sürebilir..."),
    ("  still downloading the speech recognition model (1.6 GB), 3 min so far. Please wait...",
     "  Konuşma tanıma modeli hâlâ indiriliyor (1.6 GB), 3 dakikadır sürüyor. Lütfen bekleyin..."),
    ("  still downloading the speech recognition model (75 MB), 30 s so far. Please wait...",
     "  Konuşma tanıma modeli hâlâ indiriliyor (75 MB), 30 saniyedir sürüyor. Lütfen bekleyin..."),
    ("  still downloading the translation model (about 1.3 GB), 12 min so far. Please wait...",
     "  Çevrimdışı çeviri modeli hâlâ indiriliyor (yaklaşık 1.3 GB), 12 dakikadır sürüyor. Lütfen bekleyin..."),
    ("  still downloading the translation model (about 1.3 GB), 30 s so far. Please wait...",
     "  Çevrimdışı çeviri modeli hâlâ indiriliyor (yaklaşık 1.3 GB), 30 saniyedir sürüyor. Lütfen bekleyin..."),
    ("Could not download the speech recognition model (no internet?).",
     "Konuşma tanıma modeli indirilemedi (internet bağlantısı yok mu?)."),
    ("Could not download the offline translation model (no internet?).",
     "Çevrimdışı çeviri modeli indirilemedi (internet bağlantısı yok mu?)."),
    ("The internet is needed only the first time. Check it and try again.",
     "İnternet yalnızca ilk seferde gerekir. Bağlantıyı kontrol edip yeniden deneyin."),
    ("Speech recognition model downloaded.", "Konuşma tanıma modeli indirildi."),
    ("Offline translation model downloaded.", "Çevrimdışı çeviri modeli indirildi."),
    ("Registered 2 NVIDIA DLL folder(s).", "Ekran kartı (GPU) için 2 NVIDIA DLL klasörü hazırlandı."),
    ("No pip-installed NVIDIA DLL folders found.", "Ekran kartı (GPU) için NVIDIA DLL klasörü bulunamadı."),
    ("No CUDA device detected.", "Kullanılabilir ekran kartı (NVIDIA GPU) bulunamadı."),
    ("CUDA check failed: CUDA driver version is insufficient for CUDA runtime version",
     "Ekran kartı (GPU) denetimi başarısız oldu: CUDA driver version is insufficient for CUDA runtime version"),
    ("CUDA library cudnn64_9.dll could not be loaded.",
     "Ekran kartı (GPU) kütüphanesi cudnn64_9.dll yüklenemedi."),
    ("Loading speech recognition model 'large-v3-turbo' on CUDA...",
     "Konuşma tanıma modeli 'large-v3-turbo' ekran kartına (GPU) yükleniyor..."),
    ("Loading speech recognition model 'tiny' on CPU...",
     "Konuşma tanıma modeli 'tiny' işlemciye (CPU) yükleniyor..."),
    ("Transcribing on GPU...", "Konuşmalar yazıya dökülüyor: ekran kartı (GPU) kullanılıyor..."),
    ("Transcribing on CPU...", "Konuşmalar yazıya dökülüyor: işlemci (CPU) kullanılıyor..."),
    ("Using CPU (slower).", "İşlemci (CPU) kullanılacak (daha yavaş)."),
    ("GPU transcription failed (RuntimeError: CUDA failed with error out of memory). Falling back to CPU.",
     "Ekran kartında (GPU) konuşma tanıma başarısız oldu (RuntimeError: CUDA failed with error out of memory). "
     "İşlemciyle (CPU) devam ediliyor."),
    ("GPU transcription failed (RuntimeError: first line of a long error",
     "Ekran kartında (GPU) konuşma tanıma başarısız oldu (RuntimeError: first line of a long error"),
    ("last line of a long error). Falling back to CPU.",
     "last line of a long error). İşlemciyle (CPU) devam ediliyor."),
    ("Could not load the speech recognition model (ValueError: Invalid model size 'huge')",
     "Konuşma tanıma modeli yüklenemedi (ValueError: Invalid model size 'huge')"),
    ("Detected language: en (probability 0.98)", "Algılanan konuşma dili: en (olasılık 0.98)"),
    ("  Not sure about the spoken language. If the subtitles look wrong, choose the spoken language "
     "instead of Auto-detect.",
     "  Konuşulan dil kesin anlaşılamadı. Altyazılar yanlış görünürse “Otomatik algıla” yerine "
     "konuşulan dili seçin."),
    ("  Skipped unclear sound at 1:02:03 (not speech?): Hmm, mm. (Does it say: no?)",
     "  1:02:03 anındaki belirsiz ses atlandı (konuşma olmayabilir): Hmm, mm. (Does it say: no?)"),
    ("  Skipped subtitle credit at 12:34 (not speech?): Subtitles by the Amara.org community",
     "  12:34 anındaki altyazı imzası atlandı (konuşma olmayabilir): Subtitles by the Amara.org community"),
    ("  Skipped a repeated line at 0:45: Thank you very much for watching.",
     "  0:45 anında tekrarlanan bir satır atlandı: Thank you very much for watching."),
    ("No speech was found in this video (only silence, music or noise?).",
     "Bu videoda konuşma bulunamadı (yalnızca sessizlik, müzik ya da gürültü olabilir)."),
    ("Transcription finished: 23 subtitles. Saved lecture.en.srt",
     "Konuşma tanıma bitti: 23 altyazı. Kaydedildi: lecture.en.srt"),
    (r"Saved subtitled video: C:\Videos\talk (2).tr.subtitled.mp4",
     r"Altyazılı video kaydedildi: C:\Videos\talk (2).tr.subtitled.mp4"),
    ("Saved talk (2).tr.srt", "Kaydedildi: talk (2).tr.srt"),
    ("The previous talk.tr.srt was kept as talk.tr.srt.bak-20261104-101500",
     "talk.tr.srt dosyasının önceki hâli talk.tr.srt.bak-20261104-101500 adıyla saklandı."),
    ("Could not save the subtitles (Permission denied). Choose another output folder.",
     "Altyazılar kaydedilemedi (Permission denied). Başka bir çıktı klasörü seçin."),
    ("Burning subtitles into talk.tr.subtitled.mp4 (re-encoding, this may take a while)...",
     "Altyazılar videoya gömülüyor: talk.tr.subtitled.mp4 (video yeniden kodlanıyor, biraz sürebilir)..."),
    ("Could not create the subtitled video (ffmpeg failed).",
     "Altyazılı video oluşturulamadı (ffmpeg hata verdi)."),
    ("Translating 23 subtitles (12 sentences), en -> tr.",
     "23 altyazı çevriliyor (12 cümle), en → tr."),
    ("Translating 2 long sentence(s) again, one subtitle at a time (part of the translation was missing).",
     "Çevirisi eksik kalan 2 uzun cümle, her altyazı ayrı ayrı olmak üzere yeniden çevriliyor."),
    ("Translating en -> zh...", "Çeviri: en → zh..."),
    ("Unknown translator: 'deepl'", "Bilinmeyen çevirmen: 'deepl'"),
    ("A target language is required.", "Bir çeviri dili seçilmesi gerekiyor."),
    ("Google Translate is not available (too many requests; the service limits how much one computer "
     "can translate). Switching to MyMemory (another online translator).",
     "Çevrimiçi çevirmen (Google) şu an kullanılamıyor (çok fazla istek; hizmet tek bir bilgisayarın "
     "yapabileceği çeviriyi sınırlıyor). Başka bir çevrimiçi çevirmene (MyMemory) geçiliyor."),
    ("Google Translate is not available (no connection to the service; is the internet on?). "
     "Switching to MyMemory (another online translator).",
     "Çevrimiçi çevirmen (Google) şu an kullanılamıyor (hizmete bağlanılamadı; internet açık mı?). "
     "Başka bir çevrimiçi çevirmene (MyMemory) geçiliyor."),
    ("Google Translate is not available (Server Error (500)). Switching to MyMemory (another online translator).",
     "Çevrimiçi çevirmen (Google) şu an kullanılamıyor (Server Error (500)). "
     "Başka bir çevrimiçi çevirmene (MyMemory) geçiliyor."),
    ("Online translation is not available (too many requests; the service limits how much one computer "
     "can translate). Switching to offline translation (NLLB).",
     "Çevrimiçi çeviri kullanılamıyor (çok fazla istek; hizmet tek bir bilgisayarın yapabileceği çeviriyi "
     "sınırlıyor). Çevrimdışı çevirmene (NLLB) geçiliyor."),
    ("Online translation is not available (no connection to the service; is the internet on?). "
     "Switching to offline translation (NLLB).",
     "Çevrimiçi çeviri kullanılamıyor (hizmete bağlanılamadı; internet açık mı?). "
     "Çevrimdışı çevirmene (NLLB) geçiliyor."),
    ("Online translation is not available (MyMemory daily limit reached). Switching to offline translation (NLLB).",
     "Çevrimiçi çeviri kullanılamıyor (MyMemory'nin günlük sınırı doldu). Çevrimdışı çevirmene (NLLB) geçiliyor."),
    ("Online translation is not available (No support for the provided language.). "
     "Switching to offline translation (NLLB).",
     "Çevrimiçi çeviri kullanılamıyor (No support for the provided language.). "
     "Çevrimdışı çevirmene (NLLB) geçiliyor."),
    ("Batch 3: line count mismatch (41 vs 42), translating line by line.",
     "3. bölümde satır sayısı tutmadı (gelen 41, beklenen 42); satırlar tek tek çevriliyor."),
    ("Translated batch 2/5.", "Çevrildi: bölüm 2/5."),
    ("Loading offline translation model (NLLB) on GPU...",
     "Çevrimdışı çeviri modeli (NLLB) ekran kartına (GPU) yükleniyor..."),
    ("Loading offline translation model (NLLB) on CPU...",
     "Çevrimdışı çeviri modeli (NLLB) işlemciye (CPU) yükleniyor..."),
    ("Could not load NLLB on GPU (CUDA failed with error out of memory). Using CPU.",
     "Çevrimdışı çevirmen (NLLB) ekran kartına (GPU) yüklenemedi (CUDA failed with error out of memory). "
     "İşlemci (CPU) kullanılıyor."),
    ("Could not load NLLB on GPU (first line of a long error",
     "Çevrimdışı çevirmen (NLLB) ekran kartına (GPU) yüklenemedi (first line of a long error"),
    ("last line of a long error). Using CPU.", "last line of a long error). İşlemci (CPU) kullanılıyor."),
    ("Translation on GPU failed (CUDA failed with error out of memory). Switching to CPU.",
     "Ekran kartında (GPU) çeviri başarısız oldu (CUDA failed with error out of memory). İşlemciye (CPU) geçiliyor."),
    ("Translation on GPU failed (first line of a long error",
     "Ekran kartında (GPU) çeviri başarısız oldu (first line of a long error"),
    ("last line of a long error). Switching to CPU.", "last line of a long error). İşlemciye (CPU) geçiliyor."),
    ("Offline translation does not support the spoken language 'haw'.",
     "Çevrimdışı çevirmen (NLLB) konuşulan dili ('haw') desteklemiyor."),
    ("If that language is wrong, choose the spoken language instead of Auto-detect; otherwise use the "
     "online translator.",
     "Bu dil yanlışsa “Otomatik algıla” yerine konuşulan dili seçin; doğruysa çevrimiçi çevirmeni (Google) "
     "kullanın."),
    ("Offline translation does not support language 'la'.",
     "Çevrimdışı çevirmen (NLLB) 'la' dilini desteklemiyor."),
    ("Use the online translator for this language.", "Bu dil için çevrimiçi çevirmeni (Google) kullanın."),
    ("Could not load the offline translation model: Unable to open file 'model.bin'",
     "Çevrimdışı çeviri modeli yüklenemedi: Unable to open file 'model.bin'"),
    ("The offline translator has no language code 'xyz_Latn'.",
     "Çevrimdışı çevirmende 'xyz_Latn' dil kodu yok."),
    ("Offline translation failed: std::bad_alloc", "Çevrimdışı çeviri başarısız oldu: std::bad_alloc"),
]

# Lines no pattern may touch (they must stay as written).
UNTOUCHED = [
    "Hello world.",
    "OSError: [WinError 3] The system cannot find the path specified",
    r"C:\Users\x\Videos\talk.tr.srt",
    "[out#0/mp4 @ 000001] Error opening output file talk.part.mp4.",
    "Saved settings to C:\\x\\settings.json",          # not an engine "Saved <subtitle file>" line
    "Translating everything now",
    "Done. Next video.",
]


def first_engine_pattern(line: str) -> int | None:
    for k, (regex, _texts) in enumerate(i18n_engine.PATTERNS):
        if re.fullmatch(regex, line.strip()):
            return k
    return None


def test_patterns() -> None:
    print("Patterns")
    i18n.set_language("tr")
    names = {"tr"}
    for k, (regex, texts) in enumerate(i18n_engine.PATTERNS):
        compiled = re.compile(regex)
        fields = {f for _, f, _, _ in string.Formatter().parse(texts["tr"]) if f}
        if not fields <= set(compiled.groupindex) or set(texts) != names:
            check(False, f"pattern {k} uses unknown groups {fields - set(compiled.groupindex)}: {regex}")
    used: set[int] = set()
    for english, turkish in SAMPLES:
        k = first_engine_pattern(english)
        if k is not None:
            used.add(k)
        got = i18n.engine_message(english)
        check(got == turkish, f"{english[:70]!r}" + ("" if got == turkish else f"\n          got {got!r}"))
    unused = [i18n_engine.PATTERNS[k][0] for k in range(len(i18n_engine.PATTERNS)) if k not in used]
    check(not unused, f"every pattern has a sample ({len(i18n_engine.PATTERNS)} patterns)"
          + "".join(f"\n          no sample: {r}" for r in unused))

    for line in UNTOUCHED:
        check(i18n.engine_message(line) == line, f"unchanged: {line!r}")

    # Multi-line message: each line on its own, unknown lines (ffmpeg output) kept.
    msg = ("Could not download the speech recognition model (no internet?).\n"
           "The internet is needed only the first time. Check it and try again.\n"
           "LocalEntryNotFoundError: An error happened while trying to locate the files")
    want = ("Konuşma tanıma modeli indirilemedi (internet bağlantısı yok mu?).\n"
            "İnternet yalnızca ilk seferde gerekir. Bağlantıyı kontrol edip yeniden deneyin.\n"
            "LocalEntryNotFoundError: An error happened while trying to locate the files")
    check(i18n.engine_message(msg) == want, "multi-line message translated line by line")

    i18n.set_language("en")
    check(all(i18n.engine_message(e) == e for e, _ in SAMPLES), "English mode returns the input unchanged")
    check(i18n.engine_message(msg) == msg, "English mode keeps multi-line messages unchanged")
    i18n.set_language("tr")


def ffmpeg(*args: str) -> None:
    subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], check=True)


def turkish_first_line(exc: BaseException) -> tuple[bool, str]:
    first = str(exc).strip().splitlines()[0]
    tr = i18n.engine_message(first)
    return tr != first, tr


def test_error_paths(out: Path) -> None:
    import engine

    print("Error paths")
    i18n.set_language("tr")
    d = out / "errors"
    d.mkdir(parents=True, exist_ok=True)
    broken = d / "broken.mp4"
    broken.write_bytes(b"this is not a video" * 100)
    silent = d / "silent.mp4"
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=160x120:rate=10", "-t", "1", "-pix_fmt", "yuv420p", str(silent))
    quiet = d / "quiet.mp4"   # a sound track with no speech
    ffmpeg("-f", "lavfi", "-i", "testsrc=size=160x120:rate=10", "-f", "lavfi", "-i", "anullsrc=r=16000:cl=mono",
           "-t", "2", "-pix_fmt", "yuv420p", "-shortest", str(quiet))
    cases = [("missing file", d / "missing.mp4", ["tr"]),
             ("broken file", broken, ["tr"]),
             ("no sound track", silent, ["tr"]),
             ("only silence", quiet, ["tr"]),
             ("no target language", silent, [])]
    for label, path, targets in cases:
        lines: list[str] = []
        try:
            engine.process_video(str(path), targets, model_size="tiny", translator="nllb",
                                 output_dir=str(d), log=lines.append)
            check(False, f"{label}: expected an error")
            continue
        except Exception as e:  # noqa: BLE001
            ok, tr = turkish_first_line(e)
            check(ok, f"{label}: {tr}")
        for line in lines:
            check(i18n.engine_message(line) != line, f"{label} log: {i18n.engine_message(line)}")
    # Unsupported language for the offline translator.
    import translation
    try:
        translation.translate_texts(["Hello."], "haw", "tr", "nllb", log=lambda m: None)
        check(False, "unsupported language: expected an error")
    except Exception as e:  # noqa: BLE001
        lines = str(e).splitlines()
        tr = [i18n.engine_message(x) for x in lines]
        check(all(a != b for a, b in zip(lines, tr)), "unsupported language: " + " / ".join(tr))


def test_real_run(video: Path, out: Path) -> None:
    import engine

    print(f"Real run (CPU, tiny, NLLB): {video.name}")
    i18n.set_language("tr")
    run_dir = out / "run"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    run_dir.mkdir(parents=True)
    copy = run_dir / video.name
    shutil.copyfile(video, copy)          # the original is only read
    lines: list[str] = []

    def log(msg: str) -> None:
        lines.extend(str(msg).split("\n"))

    engine.process_video(str(copy), ["tr", "de"], model_size="tiny", translator="nllb",
                         output_dir=str(run_dir), log=log, burn=True, vtt=True)
    # Run again as if the Turkish file had been corrected in the editor: it is kept as a backup.
    tr_srt = run_dir / f"{copy.stem}.tr.srt"
    tr_srt.write_text(tr_srt.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    engine.process_video(str(copy), ["tr"], source_lang="en", model_size="tiny", translator="nllb",
                         output_dir=str(run_dir), log=log)
    english = [x for x in lines if i18n.engine_message(x) == x]
    print(f"  {len(lines)} log lines, {len(lines) - len(english)} translated, {len(english)} still English")
    for x in lines:
        print("    " + ("EN  " if x in english else "TR  ") + i18n.engine_message(x))
    check(not english, "every log line of the real run is Turkish")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true", help="patterns only (no ffmpeg, no models)")
    parser.add_argument("--video", default=DEFAULT_VIDEO)
    parser.add_argument("--out", default=None, help="work folder (default: a new temp folder)")
    args = parser.parse_args()

    test_patterns()
    if not args.quick:
        out = Path(args.out) if args.out else Path(tempfile.mkdtemp(prefix="i18n_engine_"))
        test_error_paths(out)
        import sample_media
        video = args.video or sample_media.make_sample_video(str(out))
        if video and Path(video).is_file():
            test_real_run(Path(video), out)
        else:
            print(f"Real run skipped: no video (use --video; making a test video needs Windows speech)")
    print()
    if failures:
        print(f"{len(failures)} FAILED")
        sys.exit(1)
    print("All passed.")


if __name__ == "__main__":
    main()
