r"""Checks for transcript.py, readable transcripts of subtitles (plain python, no pytest):

    .venv\Scripts\python.exe tests\test_transcript.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import transcript  # noqa: E402
from subtitles import Cue, write_srt  # noqa: E402

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    print(("  ok    " if cond else "  FAIL  ") + msg)
    if not cond:
        failures.append(msg)


CUES = [
    Cue(0.0, 2.0, "Merhaba, bugün oyun\nterapisini konuşacağız."),
    Cue(2.1, 4.0, "İlk konu *önemli* [not] #1."),
    Cue(4.1, 5.0, ""),                                   # emptied in the editor: skipped
    Cue(8.0, 9.5, "Uzun bir sessizlikten sonra"),
    Cue(9.6, 11.0, "yeni bir paragraf başlıyor."),
] + [Cue(12.0 + 2 * k, 13.5 + 2 * k, f"Cümle {k + 1}.") for k in range(7)] \
  + [Cue(3725.0, 3727.0, "Bir saat sonra.")]


def test_paragraphs() -> None:
    print("== paragraphs")
    paras = transcript.paragraphs(CUES)
    starts = [round(s, 1) for s, _ in paras]
    check(starts[:2] == [0.0, 8.0], f"new paragraph after a pause > 2 s: {starts}")
    check(paras[0][1] == "Merhaba, bugün oyun terapisini konuşacağız. İlk konu *önemli* [not] #1.",
          f"cues joined, line breaks removed: {paras[0][1]!r}")
    check(all(text.count(".") <= transcript.PARAGRAPH_SENTENCES + 1 for _, text in paras),
          f"at most ~{transcript.PARAGRAPH_SENTENCES} sentences per paragraph: {[t for _, t in paras]}")
    check(paras[-1] == (3725.0, "Bir saat sonra."), f"last paragraph: {paras[-1]}")
    cjk = transcript.paragraphs([Cue(0, 1, "我们今天\n讨论游戏治疗。"), Cue(1.1, 2, "这很重要。")])
    check(cjk == [(0, "我们今天讨论游戏治疗。这很重要。")], f"Chinese joined without spaces: {cjk}")
    check(transcript._clock(3725.4) == "01:02:05", "timestamps [hh:mm:ss]")


def test_formats(d: str) -> None:
    import docx

    print("== formats")
    txt = transcript.export_transcript(CUES, os.path.join(d, "a.txt"), "Oyun Terapisi - 3. Gün", "tr",
                                       date="04.11.2026")
    lines = Path(txt).read_text(encoding="utf-8").split("\n")
    check(lines[:4] == ["Oyun Terapisi - 3. Gün", "======================", "Dil: Türkçe · Tarih: 04.11.2026", ""],
          f"txt header: {lines[:4]}")
    check(lines[4].startswith("[00:00:00] Merhaba,") and "[01:02:05] Bir saat sonra." in lines,
          f"txt paragraphs: {lines[4][:40]!r}")
    plain = transcript.export_transcript(CUES, os.path.join(d, "b.txt"), "T", "en", timestamps=False)
    body = Path(plain).read_text(encoding="utf-8")
    check("[00:" not in body and "Language: English · Date: " in body, "txt without timestamps, English labels")

    md = Path(transcript.export_transcript(CUES, os.path.join(d, "a.md"), "Ders *1*", "de")).read_text(encoding="utf-8")
    check(md.startswith("# Ders \\*1\\*\n\n*Language: German · Date: "), f"md header: {md[:50]!r}")
    check("**[00:00:00]** Merhaba" in md and "\\*önemli\\* \\[not\\] \\#1." in md, "md timestamps, escaping")

    path = transcript.export_transcript(CUES, os.path.join(d, "a.docx"), "Oyun Terapisi", "tr")
    doc = docx.Document(path)
    paras = doc.paragraphs
    check(paras[0].style.name == "Title" and paras[0].text == "Oyun Terapisi", "docx title")
    check(paras[1].text.startswith("Dil: Türkçe · Tarih: ") and paras[1].runs[0].font.size.pt == 9,
          f"docx header: {paras[1].text!r}")
    body = paras[2:]
    check(len(body) == len(transcript.paragraphs(CUES)), f"docx: one paragraph each ({len(body)})")
    stamp = body[0].runs[0]
    check(stamp.text == "[00:00:00] " and stamp.font.color.rgb == transcript_grey() and stamp.font.size.pt == 8,
          "docx: small grey timestamp")
    check(body[0].runs[1].text.startswith("Merhaba, bugün"), "docx: text run")
    check(doc.core_properties.title == "Oyun Terapisi" and doc.core_properties.language == "tr", "docx properties")
    rtl = docx.Document(transcript.export_transcript([Cue(0, 1, "مرحبا بكم.")], os.path.join(d, "ar.docx"), "T", "ar"))
    check(rtl.paragraphs[2]._p.pPr.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}bidi") is not None, "Arabic: right-to-left")
    check(not [f for f in os.listdir(d) if f.endswith(".part")], "no .part files left")

    try:
        transcript.export_transcript(CUES, os.path.join(d, "a.pdf"), "T", "tr")
        check(False, "pdf: expected an error")
    except ValueError as e:
        check("Unknown transcript format: pdf" == str(e), f"pdf: {e}")


def transcript_grey():
    from docx.shared import RGBColor
    return RGBColor(0x80, 0x80, 0x80)


def test_srt(d: str) -> None:
    print("== export_srt_transcript")
    srt = os.path.join(d, "lesson 1 (final).en.srt")
    write_srt(CUES, srt)
    out = transcript.export_srt_transcript(srt, os.path.join(d, "x.md"), "md", timestamps=False)
    md = Path(out).read_text(encoding="utf-8")
    check(md.startswith("# lesson 1 (final)\n\n*Language: English · ") and "[00:" not in md,
          f"title/language from the file name: {md[:50]!r}")
    srt2 = os.path.join(d, "notes.srt")
    write_srt(CUES[:2], srt2)
    txt = Path(transcript.export_srt_transcript(srt2, os.path.join(d, "n.txt"))).read_text(encoding="utf-8")
    check(txt.startswith("notes\n=====\nDate: "), f"no language in the name: {txt[:30]!r}")


def main() -> int:
    test_paragraphs()
    with tempfile.TemporaryDirectory(prefix="test_transcript_") as d:
        test_formats(d)
        test_srt(d)
    print(f"\n{'ALL OK' if not failures else f'{len(failures)} FAILED'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
