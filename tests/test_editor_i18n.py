"""Editor language tests (plain Python, no pytest):  .venv\\Scripts\\python.exe tests\\test_editor_i18n.py

Opens the real editor window in Turkish and in English on a small generated SRT (in a
temporary folder) and, if available, a real short video (read only; set EDITOR_TEST_VIDEO
to use another one). Burning uses the fake engine. Message boxes are replaced by
recorders. Checks that every visible text is in the window's language, never a raw key,
and that no button is cut off at the window's minimum size.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import string
import sys
import tempfile
import time

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import fake_engine  # noqa: E402

sys.modules["engine"] = fake_engine
import tkinter as tk  # noqa: E402
from tkinter import messagebox, ttk  # noqa: E402

DIALOGS: list[tuple[str, str, str]] = []   # (kind, title, message)
ANSWERS: dict = {}


def _recorder(name, default):
    def show(title=None, message=None, **kw):
        DIALOGS.append((name, title or "", message or ""))
        return ANSWERS.get(name, default)
    return show


for _name, _default in (("showinfo", "ok"), ("showwarning", "ok"), ("showerror", "ok"),
                        ("askyesno", False), ("askyesnocancel", None)):
    setattr(messagebox, _name, _recorder(_name, _default))

import editor  # noqa: E402
import i18n  # noqa: E402
import i18n_editor  # noqa: E402
from i18n import t  # noqa: E402

editor.get_engine = lambda: fake_engine
fake_engine.STEP_DELAY = 0.01
STRINGS = i18n_editor.STRINGS
i18n.t("ed_title")                     # loads every text table
ALL_KEYS = set(i18n._strings)          # keys of all windows' tables
TMP = tempfile.mkdtemp(prefix="test_editor_i18n_")
import sample_media  # noqa: E402  (made-up test video, see tests/sample_media.py)
VIDEO = os.environ.get("EDITOR_TEST_VIDEO") or sample_media.make_sample_video(TMP, speech=False) or ""
failures: list[str] = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        failures.append(msg)
        print("FAIL:", msg)


def pump(root, seconds: float = 0.05) -> None:
    end = time.time() + seconds
    while True:
        root.update()
        if time.time() >= end:
            break
        time.sleep(0.01)


def wait(root, cond, timeout: float = 20) -> bool:
    end = time.time() + timeout
    while not cond():
        if time.time() > end:
            return False
        pump(root, 0.02)
    return True


# ---------------------------------------------------------------- helpers

def make_srts(folder: str) -> tuple[str, str]:
    """A small translated SRT with one cue per readability problem, plus its original."""
    Cue = editor.subtitles.Cue
    texts = ["Merhaba, DİLGEM eğitimine hoş geldiniz.",
             "Bugün oyun terapisini konuşacağız ve çocukların oyunla kendilerini nasıl "
             "ifade ettiğini birlikte göreceğiz, sonra da örneklere bakacağız.",   # too long
             "Çok hızlı okunması gereken uzun bir cümle burada.",                # too fast
             "Bu altyazı sonrakiyle çakışıyor.",                                   # overlap
             "Teşekkürler, görüşmek üzere!"]
    times = [(1.0, 4.0), (4.5, 9.0), (9.5, 10.5), (11.0, 14.0), (13.5, 16.0)]
    cues = [Cue(s, e, x) for (s, e), x in zip(times, texts)]
    originals = [Cue(s, e, f"Original sentence {i + 1}.") for i, (s, e) in enumerate(times)]
    os.makedirs(folder, exist_ok=True)
    srt = os.path.join(folder, "talk.tr.srt")
    orig = os.path.join(folder, "talk.en.srt")
    editor.subtitles.write_srt(cues, srt)
    editor.subtitles.write_srt(originals, orig)
    return srt, orig


def widget_texts(widget) -> list[str]:
    """Every text a user can see in `widget` and its children."""
    out = []
    try:
        if isinstance(widget, (tk.Tk, tk.Toplevel)):
            out.append(widget.title())
        if isinstance(widget, ttk.Treeview):
            for col in widget["columns"]:
                out.append(widget.heading(col, "text"))
        elif isinstance(widget, ttk.Combobox):
            out.append(widget.get())
            out.extend(widget.cget("values") or ())
        elif isinstance(widget, tk.Text):
            out.append(widget.get("1.0", "end-1c"))
        else:
            try:
                out.append(str(widget.cget("text")))
            except tk.TclError:
                pass
    except tk.TclError:
        pass
    for child in widget.winfo_children():
        out.extend(widget_texts(child))
    return [x for x in out if x and x.strip()]


def check_language(texts: list[str], lang: str, where: str) -> None:
    """No raw key, and no fixed text left in the other language."""
    other = "en" if lang == "tr" else "tr"
    mine = {v[lang] for v in STRINGS.values()}
    foreign = {v[other] for v in STRINGS.values()} - mine
    for text in texts:
        check(text not in ALL_KEYS and not re.search(r"\bed_[a-z_]+\b", text),
              f"{where} [{lang}]: raw key shown: {text!r}")
        check(text not in foreign, f"{where} [{lang}]: text in the other language: {text!r}")


def check_not_clipped(ed, lang: str) -> None:
    """At the minimum window size every button and label is shown in full."""
    win = ed.win
    min_w, min_h = win.minsize()
    win.geometry(f"{min_w}x{min_h}")
    pump(win, 0.3)

    def walk(w):
        for child in w.winfo_children():
            if isinstance(child, (ttk.Button, ttk.Checkbutton, ttk.Combobox)) or (
                    isinstance(child, ttk.Label) and child.cget("text")
                    and child is not ed.flag_label and child.winfo_manager() == "pack"
                    and str(child.cget("foreground")) != "gray"):
                name = child.cget("text") if not isinstance(child, ttk.Combobox) else "combobox"
                check(child.winfo_ismapped(), f"[{lang}] not shown at minimum size: {name!r}")
                check(child.winfo_width() >= child.winfo_reqwidth() - 1,
                      f"[{lang}] cut off at minimum size: {name!r} "
                      f"({child.winfo_width()} < {child.winfo_reqwidth()})")
            walk(child)
    walk(win)
    ed.select(1)                     # the cue with the longest warnings (too long + too fast)
    pump(win, 0.3)
    for label in (ed.stats_label, ed.issue_label, ed.cue_label):
        check(label.winfo_width() >= label.winfo_reqwidth() - 1 and label.winfo_ismapped(),
              f"[{lang}] cut off at minimum size: {label.cget('text')!r} "
              f"({label.winfo_width()} < {label.winfo_reqwidth()})")


# ---------------------------------------------------------------- table

def test_table() -> None:
    check(isinstance(STRINGS, dict) and STRINGS, "i18n_editor.STRINGS is a non-empty dict")
    fmt = string.Formatter()
    for key, texts in STRINGS.items():
        check(key.startswith("ed_"), f"key without ed_ prefix: {key}")
        check(set(texts) == {"tr", "en"} and all(isinstance(v, str) and v for v in texts.values()),
              f"{key}: needs both tr and en")
        fields = [{f for _, f, _, _ in fmt.parse(texts.get(lang, "")) if f} for lang in ("tr", "en")]
        check(fields[0] == fields[1], f"{key}: placeholders differ {fields}")
    missing = i18n.missing_keys()
    for lang in i18n.LANGUAGES:
        mine = [k for k in missing[lang] if k in STRINGS]
        check(not mine, f"i18n.missing_keys()[{lang}] lists editor keys: {mine}")

    # every key editor.py asks for exists, and every key in the table is used
    with open(os.path.join(ROOT, "editor.py"), encoding="utf-8") as f:
        source = f.read()
    used = set(re.findall(r"""["'](ed_[a-z_]+)["']""", source))
    used |= {f"ed_burn_position_{v}" for v in editor.POSITIONS}
    used |= {f"ed_burn_size_{v}" for v in editor.SIZES}
    check(not used - set(STRINGS), f"keys used by editor.py but missing: {sorted(used - set(STRINGS))}")
    check(not set(STRINGS) - used, f"unused keys in i18n_editor.py: {sorted(set(STRINGS) - used)}")

    # no English text left in editor.py outside t(): a rough check on widget/messagebox calls
    for pattern in (r"text=\"[A-Za-z]", r"title=\"[A-Za-z]", r"messagebox\.\w+\(\s*\"",
                    r"status_var\.set\(\"[A-Za-z]"):
        hits = re.findall(pattern + r".*", source)
        check(not hits, f"hard-coded text in editor.py: {hits}")


def test_helpers() -> None:
    for lang, expect in (("tr", ("geçerli bir zaman değil", "00:01:23,450 biçiminde")),
                         ("en", ("is not a valid time", "00:01:23,450"))):
        i18n.set_language(lang)
        try:
            editor.parse_time("abc")
            check(False, "parse_time accepted 'abc'")
        except ValueError as exc:
            check(all(e in str(exc) for e in expect), f"[{lang}] parse_time error: {exc}")
        issues = editor.readability_issues("x" * 100, 0, 1.0)
        check(len(issues) == 2, f"[{lang}] too long + too fast: {issues}")
        if lang == "tr":
            check(issues[0].startswith("çok uzun") and "100,0 karakter/sn" in issues[1],
                  f"Turkish issues with decimal comma: {issues}")
            check(editor.readability_issues("", 2, 1) == ["bitiş, başlangıçtan sonra olmalı", "boş"],
                  f"Turkish end/empty issues: {editor.readability_issues('', 2, 1)}")
        else:
            check(issues[0].startswith("too long") and "100.0 chars/s" in issues[1],
                  f"English issues: {issues}")
        check(editor.parse_time("00:01:02,500") == 62.5, f"[{lang}] parse still works")

    # standalone language from settings.json
    path = os.path.join(TMP, "settings.json")
    for content, expect in (('{"ui_language": "en"}', "en"), ('{"ui_language": "tr"}', "tr"),
                            ('{"ui_language": "de"}', "tr"), ('{"model": "tiny"}', "tr"),
                            ("[1, 2]", "tr"), ('{"ui_lang', "tr"), ('{"ui_language": ["en"]}', "tr"),
                            (None, "tr")):
        if content is None:
            if os.path.exists(path):
                os.remove(path)
        else:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
        check(editor.load_ui_language(path) == expect, f"settings {content!r} -> {expect}")


def test_burn_options() -> None:
    root = tk.Tk()
    root.withdraw()
    i18n.set_language("tr")
    bo = editor.BurnOptions(root, {"position": "top", "font_size": "large", "box": True,
                                   "font": "Verdana"})
    check((bo.position_var.get(), bo.size_var.get()) == ("Üst", "Büyük"), "Turkish choices shown")
    check(bo.values() == {"position": "top", "font_size": "large", "box": True, "font": "Verdana"},
          f"Turkish values: {bo.values()}")
    texts = widget_texts(bo.frame)
    for want in ("Konum:", "Boyut:", "Yazı tipi:", "Arka plan kutusu", "Otomatik", "Alt"):
        check(want in texts, f"BurnOptions shows {want!r}: {texts}")
    bo.size_var.set("Küçük")
    i18n.set_language("en")
    bo.retranslate()
    check((bo.position_var.get(), bo.size_var.get()) == ("Top", "Small"),
          f"choice kept after switching language: {bo.position_var.get()}, {bo.size_var.get()}")
    check(bo.values()["font_size"] == "small" and bo.values()["position"] == "top",
          f"values after switching: {bo.values()}")
    check_language(widget_texts(bo.frame), "en", "BurnOptions")
    bad = editor.BurnOptions(root, {"position": "middle", "font_size": "huge"})
    check(bad.values()["position"] == "bottom" and bad.values()["font_size"] == "auto",
          "unknown saved values fall back to defaults")
    root.destroy()


# ---------------------------------------------------------------- editor window

def run_editor(lang: str) -> None:
    i18n.set_language(lang)
    folder = os.path.join(TMP, lang)
    srt, orig = make_srts(folder)
    have_video = os.path.isfile(VIDEO)
    video = VIDEO if have_video else os.path.join(folder, "missing.mp4")
    before = os.path.getmtime(VIDEO) if have_video else None

    root = tk.Tk()
    root.withdraw()
    DIALOGS.clear()
    ed = editor.open_editor(root, video, srt, original_srt=orig, log=lambda text: None)
    pump(root, 0.3)
    if have_video:
        check(wait(root, lambda: ed._preview_image is not None, 30),
              f"[{lang}] frame preview loaded: {ed.preview.cget('text')!r}")
    else:
        print(f"   (video not found, frame preview not checked: {VIDEO})")
        check(ed.preview.cget("text") == t("ed_video_not_found_short"), f"[{lang}] missing video")

    title = ed.win.title()
    check(title == t("ed_title", mark="", name="talk.tr.srt", app=t("ed_app_name")),
          f"[{lang}] window title {title!r}")
    flag = ed.flag_label.cget("text")
    check(flag == t("ed_flag_count", n=3), f"[{lang}] readability count {flag!r}")
    texts = widget_texts(ed.win)
    for key in ("ed_col_start", "ed_col_end", "ed_col_original", "ed_col_translation",
                "ed_btn_previous", "ed_btn_next", "ed_btn_play", "ed_btn_split", "ed_btn_merge",
                "ed_btn_delete", "ed_btn_undo", "ed_btn_find", "ed_start", "ed_end",
                "ed_translation", "ed_original", "ed_burn_frame", "ed_btn_save", "ed_btn_burn",
                "ed_btn_cancel", "ed_btn_open_folder", "ed_burn_position", "ed_burn_size",
                "ed_burn_font", "ed_burn_box"):
        check(t(key) in texts, f"[{lang}] {key} shown as {t(key)!r}")
    check(ed.cue_label.cget("text") == t("ed_cue_n", n=1), f"[{lang}] cue label")
    stats = ed.stats_label.cget("text")
    check(stats == t("ed_stats", duration=editor.format_number(3.0, 2), chars=len(ed.cues[0].text),
                     cps=editor.format_number(len(ed.cues[0].text) / 3.0, 1)),
          f"[{lang}] stats {stats!r}")
    if lang == "tr":
        check("Süre 3,00 sn" in stats and "karakter/sn" in stats, f"Turkish stats {stats!r}")

    # readability warnings per cue
    for index, key in ((1, "ed_issue_too_long"), (2, "ed_issue_too_fast"), (3, "ed_issue_overlap")):
        ed.select(index)
        pump(root, 0.05)
        word = t(key).split(":")[0].split("{")[0].strip()
        check(word in ed.issue_label.cget("text"),
              f"[{lang}] cue {index + 1} warns {word!r}: {ed.issue_label.cget('text')!r}")
    ed.select(0)
    ed.start_var.set("abc")
    check(not ed._apply_times(show_errors=True), f"[{lang}] invalid time rejected")
    check(ed.issue_label.cget("text") == t("ed_time_reset", error=t("ed_time_invalid", text="abc")),
          f"[{lang}] invalid time text {ed.issue_label.cget('text')!r}")
    ed.start_var.set("00:00:05,000")
    ed.end_var.set("00:00:02,000")
    ed._apply_times(show_errors=True)
    check(t("ed_time_end_before_start") in ed.issue_label.cget("text"), f"[{lang}] end before start")

    # cue operations
    check(ed.undo() is None and ed.status_var.get() == t("ed_nothing_to_undo"),
          f"[{lang}] nothing to undo: {ed.status_var.get()!r}")
    ed.select(0)
    ed.split_cue()
    check(len(ed.cues) == 6 and ed.cue_label.cget("text") == t("ed_cue_n", n=1), f"[{lang}] split")
    ed.merge_with_next()
    check(len(ed.cues) == 5, f"[{lang}] merge")
    ed.select(len(ed.cues) - 1)
    ed.merge_with_next()
    check(ed.status_var.get() == t("ed_merge_last"), f"[{lang}] merge at last: {ed.status_var.get()!r}")
    ed.select(0)
    ed.text_box.delete("1.0", "end")
    ed.text_box.insert("1.0", "Tek")
    ed._on_text_edit()
    DIALOGS.clear()
    ed.split_cue()
    check(DIALOGS and DIALOGS[-1][2] == t("ed_split_one_word") and DIALOGS[-1][1] == t("ed_app_name"),
          f"[{lang}] one-word split explained: {DIALOGS}")
    ed.undo()

    # find & replace dialog
    ed.open_find_replace()
    pump(root, 0.2)
    dlg = ed._find_dialog
    check(dlg.title() == t("ed_find_title"), f"[{lang}] find dialog title {dlg.title()!r}")
    dtexts = widget_texts(dlg)
    for key in ("ed_find_label", "ed_replace_label", "ed_match_case", "ed_find_next",
                "ed_replace", "ed_replace_all", "ed_close"):
        check(t(key) in dtexts, f"[{lang}] find dialog shows {t(key)!r}")
    check_language(dtexts, lang, "find dialog")
    for w in dlg.winfo_children()[0].winfo_children():
        for b in w.winfo_children() if isinstance(w, ttk.Frame) else ():
            check(b.winfo_width() >= b.winfo_reqwidth() - 1,
                  f"[{lang}] find dialog button cut off: {b.cget('text')!r}")
    dlg.find_var.set("yokböylebirkelime")
    dlg.find_next()
    check(dlg.status.cget("text") == t("ed_not_found"), f"[{lang}] not found text")
    dlg.find_var.set("DİLGEM")
    dlg.find_next()
    check(dlg.status.cget("text") == "" and "DİLGEM" in ed.cues[ed.current].text,
          f"[{lang}] find next")
    dlg.repl_var.set("kurumumuz")
    dlg.replace()
    check(dlg.status.cget("text") == t("ed_no_more_matches"), f"[{lang}] no more matches")
    dlg.find_var.set("altyazı")
    dlg.repl_var.set("ALTYAZI")
    dlg.replace_all()
    check(dlg.status.cget("text") == t("ed_replaced", total=1, cues=1),
          f"[{lang}] replace all text {dlg.status.cget('text')!r}")
    dlg.destroy()

    # everything shown is in this language (after the operations above)
    texts = widget_texts(ed.win)
    check_language(texts + [ed.status_var.get(), ed.issue_label.cget("text")], lang, "editor")
    check_not_clipped(ed, lang)

    # save, burn (fake engine), burn failure, close
    ed.save()
    check(ed.status_var.get() == t("ed_saved", name="talk.tr.srt"), f"[{lang}] saved text")
    check(os.path.isfile(srt + ".bak") and len(editor.subtitles.read_srt(srt)) == 5,
          f"[{lang}] saved on the copy, original kept as .bak")
    DIALOGS.clear()
    ANSWERS["askyesno"] = False
    ed.save_and_burn()
    check(ed.status_var.get() in (t("ed_burning"), "[fake] burning"), f"[{lang}] burning status")
    check(wait(root, lambda: not ed.burning and DIALOGS), f"[{lang}] burn finishes")
    pump(root, 0.2)
    out = os.path.join(folder, os.path.splitext(os.path.basename(video))[0] + ".tr.subtitled.mp4")
    check(ed.status_var.get() == t("ed_video_saved_status", path=out),
          f"[{lang}] burn done status {ed.status_var.get()!r}")
    check(DIALOGS and DIALOGS[-1][2] == t("ed_video_saved", path=out), f"[{lang}] burn done popup")

    real_burn = fake_engine.burn_video

    def failing_burn(*args, **kw):
        kw.get("log", print)("Burning subtitles into x.mp4 (re-encoding)...")
        raise RuntimeError("ffmpeg could not create the video\nlong details")

    fake_engine.burn_video = failing_burn
    DIALOGS.clear()
    ed._has_log = True
    ed.save_and_burn()
    check(wait(root, lambda: not ed.burning and DIALOGS), f"[{lang}] failing burn ends")
    pump(root, 0.2)
    fake_engine.burn_video = real_burn
    msg = DIALOGS[-1][2] if DIALOGS else ""
    check(ed.status_var.get() == t("ed_burn_failed_status"), f"[{lang}] burn failed status")
    check(msg.startswith(t("ed_burn_failed")) and t("ed_burn_failed_saved") in msg
          and t("ed_burn_failed_log") in msg, f"[{lang}] burn failed popup {msg!r}")
    check(i18n.engine_message("ffmpeg could not create the video") in msg,
          f"[{lang}] engine message passed through engine_message(): {msg!r}")

    ed.text_box.insert("end", " değişti")
    ed._on_text_edit()
    check(ed.win.title().startswith("*"), f"[{lang}] unsaved mark")
    ANSWERS["askyesnocancel"] = None
    DIALOGS.clear()
    check(ed.close() is False, f"[{lang}] cancel keeps the editor open")
    check(DIALOGS and DIALOGS[-1][2] == t("ed_save_changes"), f"[{lang}] unsaved changes question")
    ANSWERS["askyesnocancel"] = False
    check(ed.close() is True and ed.closed, f"[{lang}] close without saving")
    ANSWERS.clear()
    if have_video:
        check(os.path.getmtime(VIDEO) == before, "the real video was not touched")
    root.destroy()


def test_editor_tr() -> None:
    run_editor("tr")


def test_editor_en() -> None:
    run_editor("en")


def test_open_language_kept() -> None:
    """An open editor keeps its window texts when the language changes afterwards."""
    root = tk.Tk()
    root.withdraw()
    srt, orig = make_srts(os.path.join(TMP, "keep"))
    i18n.set_language("tr")
    ed = editor.open_editor(root, os.path.join(TMP, "missing.mp4"), srt, original_srt=orig)
    pump(root, 0.2)
    i18n.set_language("en")
    pump(root, 0.2)
    check(ed.save_btn.cget("text") == "Kaydet (Ctrl+S)", "open editor keeps its button texts")
    ed.destroy()
    i18n.set_language("en")
    ed = editor.open_editor(root, os.path.join(TMP, "missing.mp4"), srt, original_srt=orig)
    pump(root, 0.2)
    check(ed.save_btn.cget("text") == "Save  (Ctrl+S)", "reopened editor uses the new language")
    ed.destroy()
    root.destroy()


def test_standalone() -> None:
    """editor.main() takes the language from settings.json next to editor.py."""
    srt, orig = make_srts(os.path.join(TMP, "standalone"))
    real_path, real_open = editor.SETTINGS_PATH, editor.open_editor
    seen = {}

    def open_and_close(root, *args, **kw):
        ed = real_open(root, *args, **kw)
        seen["title"] = ed.win.title()
        seen["lang"] = i18n.language()
        root.after(300, ed.destroy)
        return ed

    try:
        for content, lang in (({"ui_language": "en"}, "en"), ({}, "tr")):
            editor.SETTINGS_PATH = os.path.join(TMP, "standalone", "settings.json")
            with open(editor.SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(content, f)
            i18n.set_language("en" if lang == "tr" else "tr")    # main() must change it
            editor.open_editor = open_and_close
            seen.clear()
            code = editor.main(["editor.py", os.path.join(TMP, "missing.mp4"), srt, orig])
            check(code == 0 and seen.get("lang") == lang, f"standalone {content} -> {seen}")
            check(seen.get("title", "").startswith(STRINGS["ed_title"][lang].split("{name}")[0]
                                                   .replace("{mark}", "")),
                  f"standalone title in {lang}: {seen.get('title')!r}")
    finally:
        editor.SETTINGS_PATH, editor.open_editor = real_path, real_open


def main() -> int:
    editor.enable_dpi_awareness()
    try:
        for test in (test_table, test_helpers, test_burn_options, test_editor_tr, test_editor_en,
                     test_open_language_kept, test_standalone):
            print("==", test.__name__)
            test()
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    if failures:
        print(f"{len(failures)} FAILURE(S)")
        return 1
    print("ALL TESTS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
