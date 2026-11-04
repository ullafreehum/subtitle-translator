"""Readable transcripts of subtitles: Word (.docx), plain text (.txt) or Markdown (.md).

Cues are joined into paragraphs (a new paragraph after a pause of more than ~2 s or every
few sentences), each paragraph optionally starting with its time [hh:mm:ss]. A header gives
the title, the language and the date. Used by engine.process_video(export_formats=...) and
by the editor's "Export transcript..." (export_srt_transcript).

Light imports only (python-docx is imported when a .docx is written).
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

import subtitles
from subtitles import Cue

FORMATS = ("docx", "txt", "md")

PARAGRAPH_PAUSE = 2.0       # seconds of silence that start a new paragraph
PARAGRAPH_SENTENCES = 5     # ... or after this many sentences
PARAGRAPH_CHARS = 700       # ... or this many characters (at a sentence end)

_SENTENCE_END_RE = re.compile(r"[.?!…。！？](?:[\"'”’»)\]]*)(?=\s|$)")
_ENDS_SENTENCE_RE = re.compile(r"[.?!…。！？][\"'”’»)\]]*$")
_RTL = {"ar", "fa", "he", "ur", "ps", "yi"}

# Header labels: Turkish for Turkish transcripts, English otherwise.
_LABELS = {"tr": ("Dil", "Tarih"), "en": ("Language", "Date")}
_NAMES = {"tr": {"tr": "Türkçe", "en": "İngilizce"}, "en": {"tr": "Turkish", "en": "English"}}


def _base(language: str) -> str:
    return (language or "").lower().split("-")[0].split("_")[0]


def _language_name(code: str, label_lang: str) -> str:
    """Display name of a language code in the header's language (the code if unknown)."""
    try:
        import i18n_app   # plain dict tables: "lang_de": {"tr": "Almanca", "en": "German"}
        entry = i18n_app.STRINGS.get(f"lang_{code}")
        if entry and entry.get(label_lang):
            return entry[label_lang]
    except Exception:  # noqa: BLE001
        pass
    return _NAMES.get(label_lang, {}).get(code) or code


def _clock(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def paragraphs(cues: list[Cue], pause: float = PARAGRAPH_PAUSE, max_sentences: int = PARAGRAPH_SENTENCES,
               max_chars: int = PARAGRAPH_CHARS) -> list[tuple[float, str]]:
    """Join cues into (start time, paragraph text) pairs. Empty cues are skipped."""
    out: list[tuple[float, str]] = []
    texts: list[str] = []
    start = prev_end = 0.0
    sentences = chars = 0

    def flush() -> None:
        if texts:
            # _clean joins the lines with a space, or without one between CJK/Thai characters.
            out.append((start, subtitles._clean("\n".join(texts))))

    for cue in sorted(cues, key=lambda c: c.start):
        text = subtitles._clean(cue.text or "")
        if not text:
            continue
        if texts:
            sentence_done = bool(_ENDS_SENTENCE_RE.search(texts[-1]))
            if (cue.start - prev_end > pause
                    or (sentence_done and (sentences >= max_sentences or chars >= max_chars))
                    or chars >= 2 * max_chars):
                flush()
                texts, sentences, chars = [], 0, 0
        if not texts:
            start = cue.start
        texts.append(text)
        sentences += len(_SENTENCE_END_RE.findall(text))
        chars += len(text) + 1
        prev_end = max(prev_end, cue.end)
    flush()
    return out


def _header(language: str, date: str | None) -> tuple[str, str]:
    """(label language, "Language: Turkish · Date: 2026-11-04")."""
    code = _base(language)
    label_lang = "tr" if code == "tr" else "en"
    lang_label, date_label = _LABELS[label_lang]
    if date is None:
        date = time.strftime("%d.%m.%Y" if label_lang == "tr" else "%Y-%m-%d")
    name = _language_name(code, label_lang) if re.fullmatch(r"[a-z]{2,3}", code) else language
    return label_lang, (f"{lang_label}: {name} · " if name else "") + f"{date_label}: {date}"


_MD_SPECIAL = re.compile(r"([\\`*_\[\]#<>|])")


def _md(text: str) -> str:
    """Escape Markdown syntax characters in plain text."""
    return _MD_SPECIAL.sub(lambda m: "\\" + m.group(1), text)


def _write_text(path: str, title: str, header: str, paras, timestamps: bool, md: bool) -> None:
    lines: list[str] = []
    if md:
        lines += ["# " + _md(title), "", f"*{header}*", ""]
    else:
        lines += [title, "=" * max(len(title), 3), header, ""]
    for start, text in paras:
        if md:
            text = _md(text)
            stamp = f"**[{_clock(start)}]** " if timestamps else ""
        else:
            stamp = f"[{_clock(start)}] " if timestamps else ""
        lines += [stamp + text, ""]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines).rstrip("\n") + "\n")


def _write_docx(path: str, title: str, header: str, paras, timestamps: bool, rtl: bool,
                language: str) -> None:
    try:
        from docx import Document
        from docx.oxml import OxmlElement
        from docx.shared import Pt, RGBColor
    except ImportError as e:
        raise RuntimeError("Word export needs python-docx (run setup.bat again).") from e
    grey = RGBColor(0x80, 0x80, 0x80)
    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(11)
    normal.paragraph_format.space_after = Pt(8)
    doc.core_properties.title = title
    doc.core_properties.language = language

    def bidi(paragraph) -> None:
        if rtl:   # right-to-left paragraph (Arabic, Persian, Hebrew, Urdu)
            paragraph._p.get_or_add_pPr().append(OxmlElement("w:bidi"))

    bidi(doc.add_heading(title, level=0))
    meta = doc.add_paragraph()
    run = meta.add_run(header)
    run.font.size, run.font.color.rgb = Pt(9), grey
    for start, text in paras:
        p = doc.add_paragraph()
        bidi(p)
        if timestamps:
            run = p.add_run(f"[{_clock(start)}] ")
            run.font.size, run.font.color.rgb = Pt(8), grey
        p.add_run(text)
    doc.save(path)


def export_transcript(cues: list[Cue], path: str, title: str, language: str,
                      timestamps: bool = True, fmt: str | None = None, date: str | None = None) -> str:
    """Write a readable transcript of `cues` and return its path.

    language: code ("tr", "en"...) shown in the header (Turkish labels for "tr").
    fmt: "docx", "txt" or "md" (default: from the file extension). Written to a temporary
    name first, so an existing file is never left half-written (e.g. open in Word -> error).
    """
    fmt = (fmt or Path(path).suffix.lstrip(".") or "txt").lower()
    if fmt not in FORMATS:
        raise ValueError(f"Unknown transcript format: {fmt}")
    _label_lang, header = _header(language, date)
    paras = paragraphs(cues)
    part = f"{path}.part"
    try:
        if fmt == "docx":
            _write_docx(part, title, header, paras, timestamps, _base(language) in _RTL, language)
        else:
            _write_text(part, title, header, paras, timestamps, fmt == "md")
        os.replace(part, path)
    finally:
        if os.path.exists(part):
            os.remove(part)
    return path


def export_srt_transcript(srt_path: str, out_path: str, fmt: str | None = None, timestamps: bool = True,
                          title: str | None = None, language: str | None = None) -> str:
    """Transcript of an SRT file. Title and language default to the file name:
    "lesson 1.tr.srt" -> title "lesson 1", language "tr"."""
    stem = Path(srt_path).stem
    name, _, lang = stem.rpartition(".")
    if not (name and re.fullmatch(r"[A-Za-z]{2,3}(?:-[A-Za-z]{2,4})?", lang)):
        name, lang = stem, ""
    return export_transcript(subtitles.read_srt(srt_path), out_path, title or name,
                             language or lang, timestamps, fmt)
