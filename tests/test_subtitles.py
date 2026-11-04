"""Tests for subtitles.py (plain Python, no pytest):  .venv\\Scripts\\python.exe tests\\test_subtitles.py

Checks the subtitling limits on real Whisper output (tests/fixtures/sample_segments.json,
faster-whisper "base" with word timestamps) plus edge cases, prints the resulting SRT and
compares it with the old engine output in test_output/ when that file exists.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from collections import namedtuple

sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # CJK output on a Windows console
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import subtitles as S  # noqa: E402
from subtitles import Cue, build_cues, read_srt, wrap_text, write_srt, write_vtt  # noqa: E402

FIXTURE = os.path.join(ROOT, "tests", "fixtures", "sample_segments.json")
OLD_SRT = os.environ.get("OLD_SRT", "")  # optional: an older SRT of the same speech to compare with
EPS = 0.0015          # times are rounded to milliseconds

failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)
        print("  FAIL:", msg)


def flat(text: str) -> str:
    return " ".join(text.split())


# --------------------------------------------------------------------------
# Limit checks shared by the fixture and the edge cases
# --------------------------------------------------------------------------

def check_limits(cues: list[Cue], name: str, width=42, max_lines=2, max_dur=6.0, min_dur=1.0,
                 max_cps=17.0, min_gap=0.08, allow_orphans=False) -> dict:
    """Assert the hard limits; soft ones (min duration, cps) may only be broken when the
    cue could not be extended (it already touches its neighbours). Returns statistics."""
    stats = {"cues": len(cues), "fast": 0, "short": 0}
    for k, c in enumerate(cues):
        tag = f"{name} cue {k + 1} {c.text!r}"
        lines = c.text.split("\n")
        dur = c.end - c.start
        check(len(lines) <= max_lines, f"{tag}: {len(lines)} lines")
        for line in lines:
            check(S._width(line) <= width, f"{tag}: line too wide ({S._width(line)})")
            check(line == line.strip() and line, f"{tag}: empty line / stray spaces")
        check(c.end > c.start, f"{tag}: end <= start")
        check(dur <= max_dur + EPS, f"{tag}: on screen {dur:.2f}s > {max_dur}")
        prev_end = cues[k - 1].end if k else None
        next_start = cues[k + 1].start if k + 1 < len(cues) else None
        if next_start is not None:
            check(next_start - c.end >= min_gap - EPS, f"{tag}: gap {next_start - c.end:.3f}s")
        at_end = next_start is not None and abs(next_start - min_gap - c.end) <= EPS
        at_start = prev_end is not None and abs(prev_end + min_gap - c.start) <= EPS
        if dur < min_dur - EPS:
            stats["short"] += 1
            check(at_end and (at_start or k == 0),
                  f"{tag}: {dur:.2f}s < {min_dur}s although it could be extended")
        cps = S._width(flat(c.text)) / dur
        if cps > max_cps + 0.05:
            stats["fast"] += 1
            check(at_end or dur >= max_dur - EPS,
                  f"{tag}: {cps:.1f} cps although the end could be extended")
        if not allow_orphans:
            check(len(flat(c.text).split()) > 1, f"{tag}: 1-word orphan cue")
    return stats


def srt_stats(cues: list[Cue], width=42, max_cps=17.0) -> dict:
    lines = [ln for c in cues for ln in c.text.split("\n")]
    return {
        "cues": len(cues),
        "lines wider than %d" % width: sum(S._width(ln) > width for ln in lines),
        "cues over %g cps" % max_cps: sum(S._width(flat(c.text)) / max(c.end - c.start, 1e-3)
                                          > max_cps + 0.05 for c in cues),
        "cue breaks mid-phrase": sum(S._break_class(flat(a.text).split()[-1], flat(b.text).split()[0])
                                     >= S.PLAIN for a, b in zip(cues, cues[1:])),
        "lines ending with a weak word": sum(S._break_class(ln.split()[-1], "x") == S.WEAK
                                             for c in cues for ln in c.text.split("\n")[:-1]),
        "max on screen (s)": round(max(c.end - c.start for c in cues), 2),
    }


def to_srt_text(cues: list[Cue]) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "out.srt")
        write_srt(cues, path)
        with open(path, encoding="utf-8") as f:
            return f.read()


# --------------------------------------------------------------------------
# Real data
# --------------------------------------------------------------------------

def test_fixture() -> list[Cue]:
    print("== real Whisper output (fixture)")
    with open(FIXTURE, encoding="utf-8") as f:
        segments = json.load(f)
    cues = build_cues(segments)
    stats = check_limits(cues, "fixture")
    # Every word kept, in order, with whitespace normalised.
    words = " ".join(w["word"].strip() for s in segments for w in s["words"])
    check(" ".join(flat(c.text) for c in cues) == words, "fixture: words lost or reordered")
    # Cues stay close to the speech they show.
    first, last = segments[0]["words"][0]["start"], segments[-1]["words"][-1]["end"]
    check(cues[0].start >= first - 0.5 - EPS and cues[-1].end <= last + 6, "fixture: cues drift")
    print(f"  {stats['cues']} cues; {stats['fast']} above 17 cps (speech too fast, end already at "
          f"the next cue), {stats['short']} shorter than 1 s (no room)")
    return cues


def compare_with_old(cues: list[Cue]) -> None:
    if not os.path.exists(OLD_SRT):
        print("== (old SRT not found, skipping comparison)")
        return
    old = read_srt(OLD_SRT)
    new = read_srt_roundtrip(cues)
    print("== old engine SRT vs new cues")
    a, b = srt_stats(old), srt_stats(new)
    for key in a:
        print(f"  {key:32s} old {a[key]!s:>6}   new {b[key]!s:>6}")


def read_srt_roundtrip(cues: list[Cue]) -> list[Cue]:
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "rt.srt")
        write_srt(cues, path)
        return read_srt(path)


# --------------------------------------------------------------------------
# Edge cases
# --------------------------------------------------------------------------

def words_for(text: str, start: float, step: float = 0.3, gap: float = 0.05) -> list[dict]:
    out, t = [], start
    for w in text.split():
        out.append({"start": round(t, 3), "end": round(t + step - gap, 3), "word": " " + w})
        t += step
    return out


def test_empty_and_missing_words() -> None:
    print("== empty input / missing words")
    check(build_cues([]) == [], "empty segment list")
    check(build_cues([{"start": 0, "end": 1, "text": "  ", "words": []}]) == [], "blank segment")
    cues = build_cues([{"start": 1.0, "end": 3.0, "text": " Hello there, my friend."}])
    check(len(cues) == 1 and cues[0].text == "Hello there, my friend.", f"no words key: {cues}")
    check(abs(cues[0].start - 1.0) < EPS and cues[0].end >= 3.0 - EPS, f"segment times: {cues}")
    # Words present but empty -> segment text is used.
    cues = build_cues([{"start": 0, "end": 2, "text": "Good morning.", "words": [{"start": 0, "end": 1, "word": " "}]}])
    check([c.text for c in cues] == ["Good morning."], f"empty words: {cues}")
    # Leading spaces and extra whitespace in Whisper words.
    seg = {"start": 0, "end": 2, "text": "x", "words": [
        {"start": 0.0, "end": 0.4, "word": "  Hello"}, {"start": 0.5, "end": 0.9, "word": " big  "},
        {"start": 1.0, "end": 1.6, "word": "\tworld."}]}
    check([c.text for c in build_cues([seg])] == ["Hello big world."], "word whitespace")


def test_long_segment() -> None:
    print("== 20-second segment")
    text = ("This is a very long segment that Whisper produced without any word timestamps at all, "
            "so the text has to be spread over the time proportionally. It keeps going for a while, "
            "with commas, clauses and sentences. Then it finally ends after twenty seconds of speech.")
    cues = build_cues([{"start": 10.0, "end": 30.0, "text": text}])
    check_limits(cues, "long/no-words")
    check(" ".join(flat(c.text) for c in cues) == text, "long segment text changed")
    check(len(cues) >= 4 and cues[0].start >= 10 - EPS and cues[-1].end <= 31, f"long: {len(cues)} cues")
    # Same with word timestamps.
    cues = build_cues([{"start": 10.0, "end": 30.0, "text": text, "words": words_for(text, 10.0, 20 / 45)}])
    check_limits(cues, "long/words")
    for c in cues:
        print("   ", f"{c.end - c.start:4.2f}s", c.text.replace("\n", " / "))


def test_merge_and_pauses() -> None:
    print("== merging short segments / pauses / names")
    segs = [{"start": 0.0, "end": 0.5, "text": " Okay,", "words": words_for("Okay,", 0.0)},
            {"start": 0.6, "end": 1.2, "text": " so we", "words": words_for("so we", 0.6)},
            {"start": 1.3, "end": 2.0, "text": " start now.", "words": words_for("start now.", 1.3)}]
    cues = build_cues(segs)
    check([c.text for c in cues] == ["Okay, so we start now."], f"short segments not merged: {cues}")
    # A long pause separates cues even when they would fit together.
    segs = [{"start": 0.0, "end": 1.0, "text": " Hello everyone.", "words": words_for("Hello everyone.", 0.0)},
            {"start": 4.0, "end": 5.0, "text": " Welcome back.", "words": words_for("Welcome back.", 4.0)}]
    cues = build_cues(segs)
    check(len(cues) == 2, f"long pause merged: {cues}")
    check_limits(cues, "pause")
    # No cue may end on "Dr." even with a pause after it; no orphan word.
    text = "Today we talked with Dr. Smith about the results and he told us a lot about the study."
    words = words_for(text, 0.0, 0.32)
    k = [w["word"] for w in words].index(" Dr.")
    for w in words[k + 1:]:
        w["start"] += 0.6
        w["end"] += 0.6
    cues = build_cues([{"start": 0, "end": words[-1]["end"], "text": text, "words": words}],
                      max_chars_per_line=30)
    check(not any(flat(c.text).endswith("Dr.") for c in cues), f"split after Dr.: {cues}")
    check_limits(cues, "dr-smith", width=30)
    # One word lasting 10 s (Whisper glitch) is still shown at most max_duration.
    cues = build_cues([{"start": 0, "end": 12, "text": " Hmm... okay then.", "words": [
        {"start": 0.0, "end": 10.0, "word": " Hmm..."}, {"start": 10.5, "end": 11.0, "word": " okay"},
        {"start": 11.1, "end": 11.6, "word": " then."}]}])
    check_limits(cues, "long word", allow_orphans=True)
    # Faster-whisper objects (namedtuples) work like dicts.
    Word = namedtuple("Word", "start end word probability")
    Seg = namedtuple("Seg", "start end text words")
    cues = build_cues([Seg(0.0, 1.5, " Thank you.", [Word(0.0, 0.5, " Thank", 0.9), Word(0.6, 1.5, " you.", 0.9)])])
    check([c.text for c in cues] == ["Thank you."], f"namedtuple input: {cues}")


def test_cjk() -> None:
    print("== CJK / Thai")
    zh = "我们这次在伊斯坦布尔的培训非常成功。学员们和家庭都积极参与，我们看到了很大的进步。希望下次还能再来继续培训。"
    cues = build_cues([{"start": 0.0, "end": 12.0, "text": zh}])
    check_limits(cues, "zh/no-words", allow_orphans=True)
    check("".join(c.text.replace("\n", "") for c in cues) == zh, "zh text changed / spaces added")
    for c in cues:
        print("   ", c.text.replace("\n", " / "))
        for line in c.text.split("\n"):
            check(line[0] not in "。，、！？", f"zh line starts with punctuation: {line!r}")
    # Whisper-style CJK words (no leading spaces).
    words = [{"start": 0.25 * i, "end": 0.25 * i + 0.2, "word": ch} for i, ch in enumerate(zh)]
    cues = build_cues([{"start": 0.0, "end": words[-1]["end"], "text": zh, "words": words}])
    check_limits(cues, "zh/words", allow_orphans=True)
    check("".join(c.text.replace("\n", "") for c in cues) == zh, "zh words joined with spaces")
    # Wrapping without spaces: by characters, at most 21 wide chars per 42 columns.
    w = wrap_text(zh[:40])
    check(len(w.split("\n")) == 2 and all(S._width(x) <= 42 for x in w.split("\n")), f"zh wrap: {w!r}")
    ja = "今日はとても良い天気ですね。皆さんと一緒に勉強できて本当に嬉しいです。"
    w = wrap_text(ja)
    check(len(w.split("\n")) == 2 and all(line[0] not in "。、" for line in w.split("\n")), f"ja wrap: {w!r}")
    print("    ja:", w.replace("\n", " / "))
    th = "สวัสดีครับวันนี้เรามาเรียนภาษาไทยด้วยกันนะครับขอบคุณมากครับที่มาร่วมการอบรมในครั้งนี้"
    w = wrap_text(th)
    lines = w.split("\n")
    check(len(lines) == 2 and "".join(lines) == th, f"th wrap: {w!r}")
    check(all(not S._char_width(line[0]) == 0 for line in lines), f"th line starts with a mark: {w!r}")
    print("    th:", w.replace("\n", " / "))


def test_wrap_text() -> None:
    print("== wrap_text")
    check(wrap_text("Hello  world ") == "Hello world", "short text")
    check(wrap_text("Hello\nworld") == "Hello world", "line breaks re-flowed")
    t = "When we arrived at the hotel late at night, everyone was already asleep upstairs."
    w = wrap_text(t)
    check(w.split("\n")[0].endswith("night,"), f"break after comma: {w!r}")
    t = "I think it was a really good training and the families were very happy with it"
    top, bottom = wrap_text(t).split("\n")
    check(len(bottom) >= len(top) - 4 and max(len(top), len(bottom)) <= 42, f"balance: {top!r} / {bottom!r}")
    check(not top.endswith((" the", " a", " and")), f"weak line end: {top!r}")
    # Never inside "Dr. Smith" or a number -- as long as another layout fits the width.
    t = "We finally met Dr. Smith at the hospital entrance yesterday"
    for width in (34, 38, 42):
        lines = wrap_text(t, width).split("\n")
        check(not lines[0].endswith("Dr."), f"split after Dr. at width {width}: {lines}")
    t = "In the end the whole project cost us 25 000 euros, which was more than planned"
    lines = wrap_text(t).split("\n")
    check(not lines[0].endswith(" 25"), f"number split: {lines}")
    long = " ".join(["word"] * 40)                                   # 199 chars, too long
    lines = wrap_text(long).split("\n")
    check(len(lines) == 2 and abs(len(lines[0]) - len(lines[1])) <= 5, f"too long -> 2 balanced: {lines}")
    check(len(wrap_text(long, 42, 3).split("\n")) == 3, "max_lines=3")
    check(wrap_text("x" * 100) == "x" * 100, "single unbreakable word")


def test_srt_io() -> None:
    print("== read_srt / write_srt / write_vtt")
    messy = ("\ufeff1\r\n00:00:01,000 --> 00:00:02,500\r\nHello\r\n  world  \r\n"
             "2  \r\n00:00:03,000-->00:00:04,000\r\n  Second cue\r\n\r\n\r\n"
             " 3 \r\n00:00:05.5 --> 00:00:06,250 X1:0 X2:10\r\nThird\r\n\r\n"
             "4\r\n00:00:07,000 --> 00:00:08,000\r\n\r\n"                       # empty cue
             "5\r\n1:02:03,004 --> 01:02:04,000\r\n2008\r\nwas a year")
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "messy.srt")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(messy)
        cues = read_srt(path)
        expected = [Cue(1.0, 2.5, "Hello\nworld"), Cue(3.0, 4.0, "Second cue"),
                    Cue(5.5, 6.25, "Third"), Cue(7.0, 8.0, ""), Cue(3723.004, 3724.0, "2008\nwas a year")]
        check(len(cues) == len(expected), f"messy srt: {cues}")
        for got, exp in zip(cues, expected):
            check(abs(got.start - exp.start) < 1e-6 and abs(got.end - exp.end) < 1e-6
                  and got.text == exp.text, f"messy srt: {got} != {exp}")
        # Round trip (texts are re-wrapped on write, so compare wrapped texts).
        src = [Cue(0.0, 1.234, "Short one."),
               Cue(1.5, 4.0, "A much longer cue that certainly needs two lines on screen."),
               Cue(3661.001, 3662.999, "İstanbul'da çok güzel bir eğitim oldu, teşekkürler!")]
        out = os.path.join(tmp, "rt.srt")
        write_srt(src, out)
        with open(out, encoding="utf-8") as f:
            raw = f.read()
        check("01:01:01,001 --> 01:01:02,999" in raw, "SRT time format")
        back = read_srt(out)
        check([(c.start, c.end, c.text) for c in back] ==
              [(c.start, c.end, wrap_text(c.text)) for c in src], f"round trip: {back}")
        check(read_srt_roundtrip(back) == back, "second round trip changed cues")
        # A cue emptied in the editor and a cue that is only a number survive a round trip.
        odd = [Cue(0.0, 1.0, "One"), Cue(1.5, 2.0, ""), Cue(2.5, 3.0, "42"), Cue(3.5, 4.0, "7"),
               Cue(4.5, 5.0, "End")]
        write_srt(odd, out)
        back = read_srt(out)
        check([c.text for c in back] == ["One", "", "42", "7", "End"], f"empty/number cues: {back}")
        # Without blank lines and index numbers, a number-only cue is still text.
        with open(out, "w", encoding="utf-8") as f:
            f.write("00:00:01,000 --> 00:00:02,000\n42\n00:00:03,000 --> 00:00:04,000\nNext\n")
        check([c.text for c in read_srt(out)] == ["42", "Next"], f"number cue, no indices: {read_srt(out)}")
        vtt = os.path.join(tmp, "rt.vtt")
        write_vtt(src + [Cue(5, 6, "Tom & Jerry <3")], vtt)
        with open(vtt, encoding="utf-8") as f:
            v = f.read()
        check(v.startswith("WEBVTT\n\n00:00:00.000 --> 00:00:01.234\nShort one.\n\n"), f"vtt: {v[:60]!r}")
        check("Tom &amp; Jerry &lt;3" in v, "vtt escaping")


def test_cues_for_texts(cues: list[Cue]) -> None:
    """Translations laid out over their sentences' original times (engine re-timing)."""
    print("\n== cues_for_texts (re-timed translations)")
    # Sentence groups of the fixture cues, each "translated" into a longer text.
    groups, cur = [], []
    for k, c in enumerate(cues):
        cur.append(k)
        if flat(c.text)[-1] in ".?!":
            groups.append(cur)
            cur = []
    if cur:
        groups.append(cur)
    longer = {g[0]: " ".join(flat(cues[i].text) for i in g) + " Yani gerçekten öyle düşünüyorum, evet."
              for g in groups}
    items = [([(cues[i].start, cues[i].end) for i in g], longer[g[0]]) for g in groups]
    out = S.cues_for_texts(items)
    stats = check_limits(out, "retimed", allow_orphans=True)
    print(f"  {len(cues)} original cues, {len(groups)} sentences -> {len(out)} cues; {stats}")
    check(flat(" ".join(c.text for c in out)) == flat(" ".join(t for _, t in items)), "text preserved")
    check(all(sum(flat(c.text) in t for _, t in items) >= 1 for c in out), "a cue never mixes two sentences")
    check(all(b.start - a.end >= 0.08 - 1e-9 for a, b in zip(out, out[1:])), "gaps >= 80 ms (exact)")
    check(out[0].start >= cues[0].start - 0.5 and out[-1].end <= cues[-1].end + 6.0, "within the speech")
    for g, (_, text) in zip(groups, items):   # each sentence stays near its own time span
        inside = [c for c in out if c.start >= cues[g[0]].start - 0.6 and c.end <= cues[g[-1]].end + 6.0]
        check(text.split()[0] in " ".join(c.text for c in inside), f"sentence at its time: {text[:30]!r}")

    # Two intervals with a long pause: the text is not shown over the pause.
    out = S.cues_for_texts([([(0.0, 3.0), (8.0, 11.0)],
                             "Birinci bölümde bunu söylüyoruz ve sonra bir süre susuyoruz. "
                             "İkinci bölümde ise konuşmaya devam ediyoruz.")])
    check_limits(out, "pause", allow_orphans=True)
    check(not any(c.start < 7.5 < c.end for c in out), f"no cue over the pause: {out}")
    # Overlapping / touching spans and a CJK text: still no overlaps, gaps kept.
    out = S.cues_for_texts([([(0.0, 1.0)], "Kısa."), ([(0.95, 2.0)], "Yine kısa."),
                            ([(2.0, 4.0)], "我们今天讨论游戏治疗的基本原则。")])
    check(all(b.start - a.end >= 0.08 - 1e-9 for a, b in zip(out, out[1:])), f"overlapping spans: {out}")
    check("我们今天讨论游戏治疗的基本原则。" in "".join(c.text.replace("\n", "") for c in out), "CJK kept")
    check(S.cues_for_texts([([(1.0, 2.0)], "  "), ([], "x")]) == [], "empty texts / no times -> no cues")


def main() -> int:
    cues = test_fixture()
    test_cues_for_texts(cues)
    test_empty_and_missing_words()
    test_long_segment()
    test_merge_and_pauses()
    test_cjk()
    test_wrap_text()
    test_srt_io()
    compare_with_old(cues)
    print("\n== new SRT for the fixture\n")
    print(to_srt_text(cues))
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
