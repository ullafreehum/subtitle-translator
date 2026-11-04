"""GUI tests with the fake engine (plain Python, no pytest):  .venv\\Scripts\\python.exe tests\\test_gui.py

Drives the real Tk windows of app.py and editor.py programmatically (windows flash up
briefly). Message boxes are replaced by recorders; settings and all output files go to a
temporary folder, so the user's settings.json is never touched. The main window's flow
runs in both interface languages (Turkish and English).
"""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import string
import sys
import tempfile
import time
import types

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import fake_engine  # noqa: E402

sys.modules["engine"] = fake_engine
from tkinter import messagebox  # noqa: E402

DIALOGS: list[tuple[str, str]] = []
ANSWERS: dict = {}


def _recorder(name, default):
    def show(title=None, message=None, **kw):
        DIALOGS.append((name, message or ""))
        return ANSWERS.get(name, default)
    return show


for _name, _default in (("showinfo", "ok"), ("showwarning", "ok"), ("showerror", "ok"),
                        ("askyesno", False), ("askyesnocancel", None)):
    setattr(messagebox, _name, _recorder(_name, _default))

import app  # noqa: E402
import editor  # noqa: E402
import i18n  # noqa: E402
import i18n_app  # noqa: E402
from i18n import t  # noqa: E402

TMP = tempfile.mkdtemp(prefix="test_gui_")
app.SETTINGS_PATH = os.path.join(TMP, "settings.json")
editor.get_engine = lambda: fake_engine
fake_engine.STEP_DELAY = 0.01
failures: list[str] = []
LANGS = ("tr", "en")


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


def wait(root, cond, timeout: float = 30) -> bool:
    end = time.time() + timeout
    while not cond():
        if time.time() > end:
            return False
        pump(root, 0.02)
    return True


def make_video(name: str) -> str:
    folder = os.path.join(TMP, "videos")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, name)
    open(path, "wb").close()
    return path


def new_app(settings: dict | None = None, lang: str | None = None):
    if settings is not None:
        if lang:
            settings = dict(settings, ui_language=lang)
        with open(app.SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(settings, f)
    root = app.tk.Tk()
    a = app.App(root)
    pump(root, 0.1)
    return root, a


def saved_settings() -> dict:
    with open(app.SETTINGS_PATH, encoding="utf-8") as f:
        return json.load(f)


def menu_labels(menu) -> list[str]:
    """Labels of a menu and its submenus."""
    labels = []
    end = menu.index("end")
    for i in range(0 if end is None else end + 1):
        kind = menu.type(i)
        if kind in ("separator", "tearoff"):
            continue
        labels.append(menu.entrycget(i, "label"))
        if kind == "cascade":
            labels += menu_labels(menu.nametowidget(menu.entrycget(i, "menu")))
    return labels


def visible_texts(a) -> list[str]:
    """Every text the main window shows (widgets, list entries, headings, menus)."""
    texts = [a.root.title(), a.status_var.get(), a.targets_var.get()]

    def walk(w):
        if isinstance(w, app.tk.Menu):
            return
        try:
            texts.append(str(w.cget("text")))
        except Exception:  # noqa: BLE001  (widget without a text option)
            pass
        if isinstance(w, app.ttk.Combobox):
            texts.extend(str(v) for v in w.cget("values"))
        if isinstance(w, app.tk.Listbox):
            texts.extend(w.get(0, "end"))
        if isinstance(w, app.ttk.Treeview):
            texts.extend(w.heading(c, "text") for c in w.cget("columns"))
            for iid in w.get_children():
                texts.extend(str(v) for v in w.item(iid, "values"))
        for child in w.winfo_children():
            walk(child)

    walk(a.root)
    texts += menu_labels(a.menubar)
    return [x for x in texts if x]


def check_texts(a, lang: str) -> None:
    texts = visible_texts(a)
    raw = sorted({x for x in texts if x in i18n_app.STRINGS})
    check(not raw, f"[{lang}] raw keys shown instead of texts: {raw}")
    placeholders = sorted({x for x in texts if re.search(r"\{[a-z_]+\}", x)})
    check(not placeholders, f"[{lang}] unfilled placeholders: {placeholders}")
    keylike = sorted({x for x in texts if re.fullmatch(r"[a-z]+(_[a-z0-9]+)+", x)})
    if keylike:   # keys of other tables (editor) still being written: report only
        print(f"WARN: [{lang}] texts that look like keys: {keylike}")


# ---------------------------------------------------------------- texts

def _literal(path: str, name: str):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in tree.body:
        target = getattr(node, "target", None) or (node.targets[0] if isinstance(node, ast.Assign) else None)
        if getattr(target, "id", None) == name:
            return ast.literal_eval(node.value)
    raise KeyError(name)


def test_strings() -> None:
    missing = {code: [k for k in keys if k in i18n_app.STRINGS]
               for code, keys in i18n.missing_keys().items()}
    check(not any(missing.values()), f"app texts missing: {missing}")
    fields = lambda s: {f for _, f, _, _ in string.Formatter().parse(s) if f}  # noqa: E731
    for key, texts in i18n_app.STRINGS.items():
        check(set(texts) == {"tr", "en"}, f"{key}: languages {sorted(texts)}")
        check(fields(texts.get("tr", "")) == fields(texts.get("en", "")),
              f"{key}: same placeholders in both languages")
    # Every language and translator of the real engine has a name in both languages.
    codes = _literal("engine.py", "LANGUAGES").values()
    check(not [c for c in codes if "lang_" + c not in i18n_app.STRINGS],
          f"language names missing: {[c for c in codes if 'lang_' + c not in i18n_app.STRINGS]}")
    ids = set(_literal("translation.py", "TRANSLATORS").values())
    check(all("translator_" + i in i18n_app.STRINGS for i in ids), f"translator names: {ids}")
    # English texts of the translators stay the engine's reviewed display names.
    for name, tid in _literal("translation.py", "TRANSLATORS").items():
        check(i18n_app.STRINGS["translator_" + tid]["en"] == name, f"English name of {tid}")
    i18n.set_language("tr")
    check(t("status_working", pct=42) == "Çalışıyor %42", "Turkish percent")
    check(sorted(["Çince", "Arapça", "İngilizce", "Almanca", "Ukraynaca", "Urduca"], key=app.sort_key)
          == ["Almanca", "Arapça", "Çince", "İngilizce", "Ukraynaca", "Urduca"], "Turkish order")


# ---------------------------------------------------------------- helpers

def test_parse_time() -> None:
    check(editor.parse_time("00:01:02,500") == 62.5, "parse HH:MM:SS,mmm")
    check(editor.parse_time("1:02.5") == 62.5, "parse MM:SS.mmm")
    for bad in ("nan", "inf", "-1", "abc", "1:2:3:4", "", "00:00:inf"):
        try:
            editor.parse_time(bad)
            check(False, f"parse_time accepted {bad!r}")
        except ValueError:
            pass
    check(not editor.readability_issues("x" * 17, 0, 1.0), "17.0 chars/s is not too fast")
    check(editor.readability_issues("x" * 18, 0, 1.0), "18 chars/s is too fast")


def test_fonts() -> None:
    check(editor._clean_font("Segoe UI") == "Segoe UI", "normal font kept")
    for bad in ("Arial',Outline=9", "a:b", "x\\y", "", None, 5):
        check(editor._clean_font(bad) == "Arial", f"unsafe font {bad!r} replaced")


def test_paths() -> None:
    folder = os.path.join(TMP, "scan")
    os.makedirs(os.path.join(folder, "sub"), exist_ok=True)
    for name in ("talk.mp4", "talk.tr.subtitled.mp4", "talk.en.part.mp4", "notes.txt",
                 os.path.join("sub", "İkinci Gün {2}.MOV")):
        open(os.path.join(folder, name), "wb").close()
    skipped: list[str] = []
    found = app.expand_paths([folder, os.path.join(folder, "notes.txt")], skipped)
    names = sorted(os.path.basename(p) for p in found)
    check(names == ["talk.mp4", "İkinci Gün {2}.MOV"], f"folder scan skips our outputs: {names}")
    check([os.path.basename(p) for p in skipped] == ["notes.txt"], f"non-video reported: {skipped}")

    i18n.set_language("en")
    check("permission" in app.friendly_error(PermissionError(13, "Permission denied", "x.srt")),
          "PermissionError explained")
    check("disk is full" in app.friendly_error(OSError(28, "No space left on device")), "disk full")
    check(app.friendly_error(RuntimeError("First line\nffmpeg details")) == "First line",
          "engine message: first line only")
    check("Unexpected error (KeyError)" in app.friendly_error(KeyError("x")), "bug: no jargon")
    check(app.folder_problem(TMP) is None, "temp folder is writable")
    check(app.folder_problem(os.path.join(TMP, "scan", "talk.mp4")) == "This is a file, not a folder.",
          "a file is not an output folder")
    i18n.set_language("tr")
    check("izin yok" in app.friendly_error(PermissionError(13, "Permission denied", "x.srt")),
          "[tr] PermissionError explained")
    check(app.friendly_error(MemoryError()) == t("err_memory"), "[tr] memory")
    check("Beklenmeyen hata (KeyError)" in app.friendly_error(KeyError("x")), "[tr] bug: no jargon")
    msg = "Video not found: x.mp4 (was it moved or renamed?)"
    check(app.friendly_error(RuntimeError(msg)) == i18n.engine_message(msg),
          "[tr] engine messages go through engine_message")
    check(app.folder_problem(os.path.join(TMP, "scan", "talk.mp4")) == "Bu bir dosya, klasör değil.",
          "[tr] a file is not an output folder")


def test_settings() -> None:
    for content in ('{"model": "tiny", "targ', "[1, 2]", "",
                    json.dumps({"target_lang": "German", "model": "large-v2", "translator": "old",
                                "burn_style": "big", "output_dir": 5, "target_langs": "Turkish",
                                "last_folder": 3, "burn": "yes", "ui_language": 7,
                                "source_lang": ["x"]})):
        with open(app.SETTINGS_PATH, "w", encoding="utf-8") as f:
            f.write(content)
        try:
            root, a = new_app()
        except Exception as exc:  # noqa: BLE001
            check(False, f"settings {content[:30]!r} crash the app: {exc!r}")
            continue
        check(a.model_var.get() in a.model_sizes and a._selected_targets(),
              f"settings {content[:30]!r} give usable defaults")
        check(i18n.language() == "tr" and a.root.title() == "Altyazı Çevirici",
              f"settings {content[:30]!r}: Turkish by default")
        root.destroy()
    # values survive a restart
    root, a = new_app({})
    a.model_var.set("base")
    a.output_var.set(os.path.join(TMP, "out"))
    a.burn_var.set(True)
    a.burn_options.font_var.set("Verdana")
    a._on_close()
    root, a = new_app()
    check((a.model_var.get(), a.output_var.get(), a.burn_var.get(), a.burn_options.values()["font"])
          == ("base", os.path.join(TMP, "out"), True, "Verdana"), "settings persist")
    root.destroy()

    # Older versions stored English display names: they become codes.
    for translator, expected in (("Online – Google Translate", "online"), ("Google (online)", "online"),
                                 ("NLLB (offline, on this PC)", "nllb"), ("online", "online")):
        root, a = new_app({"source_lang": "German", "target_langs": ["Turkish", "english", "Klingon"],
                           "translator": translator})
        check((a._source_code(), a._selected_targets(), a._translator_id())
              == ("de", ["tr", "en"], expected), f"old names migrated ({translator})")
        a._on_close()
        s = saved_settings()
        check((s["source_lang"], s["target_langs"], s["translator"], s["ui_language"])
              == ("de", ["tr", "en"], expected, "tr"), f"codes saved: {s}")
    root, a = new_app({"source_lang": "Auto-detect", "target_lang": "Arabic"})
    check(a._source_code() is None and a.source_var.get() == "Otomatik algıla"
          and a._selected_targets() == ["ar"], "old Auto-detect and single target")
    a._on_close()
    check(saved_settings()["source_lang"] == "auto", "auto-detect saved as 'auto'")
    root, a = new_app({"ui_language": "en", "source_lang": "auto"})
    check(i18n.language() == "en" and a.root.title() == "Subtitle Translator"
          and a.source_var.get() == "Auto-detect", "English from settings")
    root.destroy()


# ---------------------------------------------------------------- main window

def test_layout(lang: str) -> None:
    root, a = new_app({"target_langs": ["tr"]}, lang)
    check(i18n.language() == lang, f"[{lang}] language set before the widgets")
    check(a.root.title() == t("app_name"), f"[{lang}] title")
    check(a.start_btn.cget("text") == ("▶ Başlat" if lang == "tr" else "▶ Start"), f"[{lang}] Start")
    check(a.lang_names[:2] == [t("lang_tr"), t("lang_en")], f"[{lang}] main languages first")
    rest = a.lang_names[2:]
    check(rest == sorted(rest, key=app.sort_key), f"[{lang}] languages sorted: {rest}")
    check(list(a._source_by_name)[0] == t("auto_detect"), f"[{lang}] auto-detect first")
    tops = [a.menubar.entrycget(i, "label") for i in range(a.menubar.index("end") + 1)]
    check(tops == [t("menu_file"), t("menu_settings"), t("menu_help")], f"[{lang}] menus {tops}")
    langs = menu_labels(a.lang_menu)
    check(langs == ["Türkçe", "English"], f"[{lang}] language names in their own language: {langs}")
    check(a.empty_hint.cget("text") in (t("hint_drop"), t("hint_click_add")), f"[{lang}] hint")
    check_texts(a, lang)
    root.destroy()


def test_add_and_drop(lang: str) -> None:
    root, a = new_app({"target_langs": ["tr"]}, lang)
    sub = "drop_" + lang
    os.makedirs(os.path.join(TMP, "videos", sub), exist_ok=True)
    names = ["a b {c}.mp4", "un}balanced {x.mp4", "Gün 3 – şölen.mov"]
    paths = [make_video(os.path.join(sub, n)).replace("\\", "/") for n in names]
    paths.append(os.path.join(TMP, "x.pdf"))
    open(paths[-1], "wb").close()
    DIALOGS.clear()
    a._on_drop(types.SimpleNamespace(data=root.tk.call("list", *paths), action="copy"))
    added = sorted(os.path.basename(i.path) for i in a.items.values())
    check(added == sorted(names), f"[{lang}] drop with spaces/braces/Turkish: {added}")
    check(DIALOGS and "x.pdf" in DIALOGS[-1][1] and t("note_supported", types="")[:10]
          in DIALOGS[-1][1], f"[{lang}] non-video explained: {DIALOGS}")
    statuses = {a.tree.set(iid, "status") for iid in a.items}
    check(statuses == {t("status_waiting")}, f"[{lang}] status column: {statuses}")
    DIALOGS.clear()
    a.add_paths(paths[:1])
    check(DIALOGS and t("note_duplicates") in DIALOGS[-1][1], f"[{lang}] duplicate explained")
    empty = os.path.join(TMP, "empty folder")
    os.makedirs(empty, exist_ok=True)
    DIALOGS.clear()
    a.add_paths([empty])
    check(DIALOGS and t("note_no_videos") in DIALOGS[-1][1], f"[{lang}] empty folder explained")
    root.destroy()


def test_batch(lang: str) -> None:
    out = os.path.join(TMP, "out_batch_" + lang)
    root, a = new_app({"target_langs": ["tr", "en"], "output_dir": out}, lang)
    good, bad, gone = (make_video(f"{n}_{lang}.mp4") for n in ("good", "bad", "gone"))
    fake_engine.FAIL_NAMES.add(os.path.basename(bad))
    DIALOGS.clear()
    a.start()
    check(DIALOGS and DIALOGS[-1][1] == t("nothing_waiting"), f"[{lang}] Start with an empty list explained")
    a.add_paths([good, bad, gone])
    os.remove(gone)                       # deleted after queueing
    a.target_list.selection_clear(0, "end")
    DIALOGS.clear()
    a.start()
    check(not a.running and DIALOGS and DIALOGS[-1][1] == t("need_target"), f"[{lang}] no target explained")
    a.target_list.selection_set(a.lang_codes.index("tr"))
    a.output_var.set(os.path.join(TMP, "scan", "talk.mp4"))
    DIALOGS.clear()
    a.start()
    check(not a.running and DIALOGS and t("err_not_a_folder") in DIALOGS[-1][1],
          f"[{lang}] bad output folder")
    a.output_var.set(out)

    fake_engine.STEP_DELAY = 0.05
    DIALOGS.clear()
    a.start()
    worker = a.worker
    a.start()                             # pressing Start twice
    check(a.worker is worker, f"[{lang}] second Start ignored")
    wait(root, lambda: a._current_iid is not None)
    a.tree.selection_set(a._current_iid)
    a.remove_selected()
    check(a.tree.exists(a._current_iid) and DIALOGS[-1][1] == t("remove_running"),
          f"[{lang}] running video cannot be removed (explained)")
    wait(root, lambda: a.tree.set(a._current_iid or "", "status").startswith(
        t("status_working", pct=1)[:4]) if a._current_iid else False, 10)
    wait(root, lambda: a._phase in ("phase_transcribe", "phase_translate_into"), 10)
    status = a.status_var.get()
    check(status.startswith(t("status_video", n=1, total=3) + ": "), f"[{lang}] status names the step: {status!r}")
    check(t("phase_transcribe") in status or t("phase_translate_into", lang=t("lang_en")) in status,
          f"[{lang}] step in this language: {status!r}")
    check(wait(root, lambda: not a.running and a.worker is None, 60), f"[{lang}] batch finishes")
    pump(root, 0.2)
    rows = {os.path.basename(i.path).split("_")[0]: (i.status, i.detail) for i in a.items.values()}
    check(rows["good"][0] == app.DONE and t("lang_tr") in rows["good"][1], f"[{lang}] good done: {rows}")
    check(rows["bad"] == (app.FAILED, i18n.engine_message("Simulated failure")),
          f"[{lang}] failure reason shown: {rows}")
    lost = f"Video not found: {os.path.basename(gone)} (was it moved or renamed?)"
    check(rows["gone"] == (app.FAILED, i18n.engine_message(lost)), f"[{lang}] deleted video: {rows}")
    shown = {os.path.basename(i.path).split("_")[0]: a.tree.set(iid, "status")
             for iid, i in a.items.items()}
    check(shown == {"good": t("status_done"), "bad": t("status_failed"), "gone": t("status_failed")},
          f"[{lang}] status column texts: {shown}")
    check(any(k == "showwarning" and os.path.basename(bad) in m for k, m in DIALOGS),
          f"[{lang}] batch end lists failures")
    log = a.log_text.get("1.0", "end")
    check(t("log_failed", reason="", details="").splitlines()[1].strip() in log,
          f"[{lang}] details in the log")
    check(i18n.engine_message("Extracting audio with ffmpeg...") in log, f"[{lang}] engine log lines shown")
    check(a.status_var.get().startswith(t("status_finished", summary="")), f"[{lang}] finished status")

    # Cancel, then Start again
    fake_engine.FAIL_NAMES.clear()
    fake_engine.STEP_DELAY = 0.2
    a.start()
    wait(root, lambda: a._current_iid is not None)
    a.cancel()
    check(wait(root, lambda: not a.running and a.worker is None, 30), f"[{lang}] cancel stops the batch")
    pump(root, 0.2)
    check(app.CANCELLED in [i.status for i in a.items.values()], f"[{lang}] item marked Cancelled")
    check(t("status_cancelled") in [a.tree.set(iid, "status") for iid in a.items],
          f"[{lang}] Cancelled shown")
    fake_engine.STEP_DELAY = 0.01
    a.start()
    check(wait(root, lambda: not a.running and a.worker is None, 60), f"[{lang}] restart after cancel")
    pump(root, 0.2)
    check(all(i.status == app.DONE for i in a.items.values() if os.path.exists(i.path)),
          f"[{lang}] all done after retry")
    check_texts(a, lang)
    root.destroy()


def _ui_state(a) -> dict:
    return {
        "items": [(i.path, i.status, i.result is not None, i.error) for i in a.items.values()],
        "source": a._source_code(), "targets": a._selected_targets(),
        "translator": a._translator_id(), "model": a.model_var.get(),
        "output": a.output_var.get(), "burn": a.burn_var.get(), "review": a.review_var.get(),
        "style": a.burn_options.values(), "log": a.log_text.get("1.0", "end-1c"),
        "selection": a.tree.selection(),
        "size": (a.root.winfo_width(), a.root.winfo_height()),
    }


def _invoke_language(a, name: str) -> None:
    menu = a.lang_menu
    index = next(i for i in range(menu.index("end") + 1) if menu.entrycget(i, "label") == name)
    menu.invoke(index)


def test_language_switch() -> None:
    out = os.path.join(TMP, "out_switch")
    root, a = new_app({"target_langs": ["tr", "en"], "output_dir": out}, "tr")
    good, bad = make_video("switch good.mp4"), make_video("switch bad.mp4")
    fake_engine.FAIL_NAMES.add("switch bad.mp4")
    a.add_paths([good, bad])
    a.start()
    check(wait(root, lambda: not a.running and a.worker is None, 60), "switch: batch finishes")
    pump(root, 0.2)
    fake_engine.FAIL_NAMES.clear()
    a.add_paths([make_video("switch waiting.mp4")])
    # Change every option.
    a.source_var.set(a._lang_name("de"))
    a.target_list.selection_clear(0, "end")
    for code in ("tr", "fr", "ar"):
        a.target_list.selection_set(a.lang_codes.index(code))
    a.translator_var.set(t("translator_online"))
    a.model_var.set("small")
    a.output_var.set(os.path.join(TMP, "out_switch2"))
    a.burn_var.set(True)
    a.review_var.set(True)
    a.burn_options.font_var.set("Tahoma")
    a.burn_options.box_var.set(True)
    a.root.geometry("1050x820")
    first = next(iter(a.items))
    a.tree.selection_set(first)
    pump(root, 0.2)
    before = _ui_state(a)
    old_tree = a.tree

    DIALOGS.clear()
    _invoke_language(a, "English")
    pump(root, 0.2)
    after = _ui_state(a)
    check(a.tree is not old_tree and i18n.language() == "en", "switch: rebuilt in English")
    for key in before:
        check(before[key] == after[key], f"switch keeps {key}: {before[key]!r} -> {after[key]!r}")
    check(a.root.title() == "Subtitle Translator" and a.start_btn.cget("text") == "▶ Start",
          "switch: English texts")
    check(a.source_var.get() == "German" and a.translator_var.get() == "Online – Google Translate",
          f"switch: choices shown in English: {a.source_var.get()!r}, {a.translator_var.get()!r}")
    statuses = [a.tree.set(iid, "status") for iid in a.items]
    check(statuses == ["Done", "Failed", "Waiting"], f"switch: statuses in English: {statuses}")
    check("Turkish" in a.tree.set(first, "result"), "switch: result column in English")
    check(not DIALOGS, f"switch while idle: no message {DIALOGS}")
    check(saved_settings()["ui_language"] == "en", "switch: saved")
    check_texts(a, "en")
    a._open_item_editor(first, "tr")       # results kept: the editor still opens
    check(len(a.editors) == 1, "switch: review still works")
    for ed in list(a.editors.values()):
        ed.close()
    pump(root, 0.1)

    _invoke_language(a, "Türkçe")
    pump(root, 0.2)
    again = _ui_state(a)
    for key in before:
        check(before[key] == again[key], f"switch back keeps {key}")
    check(a.start_btn.cget("text") == "▶ Başlat" and a.source_var.get() == "Almanca",
          "switch back: Turkish texts")

    # While videos are processed: the window stays as it is until the batch ends.
    fake_engine.STEP_DELAY = 0.1
    a.burn_var.set(False)
    a.start()
    check(wait(root, lambda: a._current_iid is not None, 10), "switch: batch running")
    old_tree = a.tree
    DIALOGS.clear()
    _invoke_language(a, "English")
    pump(root, 0.1)
    check(a.tree is old_tree and i18n.language() == "tr", "switch while running: not rebuilt yet")
    check(DIALOGS and DIALOGS[-1][1] == i18n_app.STRINGS["language_later"]["en"],
          f"switch while running: explained in the chosen language {DIALOGS}")
    check(saved_settings()["ui_language"] == "en", "switch while running: choice saved")
    check(wait(root, lambda: not a.running and a.worker is None, 60), "switch: batch finishes")
    pump(root, 0.3)
    check(a.tree is not old_tree and i18n.language() == "en", "switch applied after the batch")
    check(a.status_var.get().startswith("Finished: "), f"summary re-shown in English: {a.status_var.get()!r}")
    check([a.tree.set(iid, "status") for iid in a.items] == ["Done", "Done", "Done"],
          "statuses after the batch in English")

    # Changing your mind during a batch: back to the current language = nothing to apply.
    for iid in a.items:
        a.items[iid].status = app.WAITING
    a.start()
    wait(root, lambda: a._current_iid is not None, 10)
    old_tree = a.tree
    _invoke_language(a, "Türkçe")
    _invoke_language(a, "English")
    check(a._pending_language is None and saved_settings()["ui_language"] == "en",
          "switch back during a batch: nothing pending")
    wait(root, lambda: not a.running and a.worker is None, 60)
    pump(root, 0.2)
    check(a.tree is old_tree and i18n.language() == "en", "no rebuild without a change")
    fake_engine.STEP_DELAY = 0.01
    a._on_close()
    root, a = new_app()
    check(i18n.language() == "en" and a.root.title() == "Subtitle Translator", "language kept on restart")
    root.destroy()


def test_review_flow() -> None:
    out = os.path.join(TMP, "out_review")
    root, a = new_app({"target_langs": ["tr", "en"], "output_dir": out,
                       "burn": True, "review": True}, "tr")
    video = make_video("review me.mp4")
    a.add_paths([video])
    a.start()
    wait(root, lambda: not a.running and a.worker is None, 60)
    pump(root, 0.2)
    iid = next(iter(a.items))
    check(a.items[iid].status == app.REVIEW, f"ready for review: {a.items[iid].status}")
    check(a.tree.set(iid, "status") == "Gözden geçirmeye hazır", "review status in Turkish")
    check(not any(c[0] == "burn_video" for c in fake_engine.calls[-3:]), "no burning before review")
    a._open_item_editor(iid, "tr")
    ed = next(iter(a.editors.values()))
    check(ed.srt_path.endswith("review me.tr.srt") and ed.has_original, "editor on the right file")
    ANSWERS["askyesno"] = False           # "Open the folder?"
    ed.save_and_burn()
    wait(root, lambda: not ed.burning, 30)
    pump(root, 0.3)
    check(a.items[iid].status == app.REVIEW, "still to review: English has no video yet")
    a._open_item_editor(iid, "en")
    ed2 = [e for e in a.editors.values() if e is not ed][0]
    ed2.save_and_burn()
    wait(root, lambda: not ed2.burning, 30)
    pump(root, 0.3)
    item = a.items[iid]
    check(item.status == app.DONE and set(item.result["burned_videos"]) == {"tr", "en"},
          f"done after both videos: {item.status} {item.result['burned_videos']}")
    check("2 video" in a.tree.set(iid, "result"), f"videos counted: {a.tree.set(iid, 'result')}")

    # Closing the main window while an editor burns: stops the burn, then quits.
    fake_engine.STEP_DELAY = 0.2
    ed.save_and_burn()
    pump(root, 0.3)
    ANSWERS["askyesno"] = True            # "Stop it and close?"
    a._on_close()
    check(a._closing and ed.closing, "closing waits for the burn to stop")
    try:
        while root.winfo_exists():
            root.update()
            time.sleep(0.02)
    except app.tk.TclError:
        pass
    check(ed.closed and not ed.burning, "burn stopped before the window closed")
    ANSWERS.pop("askyesno")
    fake_engine.STEP_DELAY = 0.01


# ---------------------------------------------------------------- editor

def test_editor() -> None:
    i18n.set_language("en")       # the checks below look for the English texts
    root = app.tk.Tk()
    root.withdraw()
    srt = os.path.join(TMP, "edit.tr.srt")
    editor.subtitles.write_srt([editor.subtitles.Cue(i * 2.0, i * 2.0 + 1.5, f"cümle {i}")
                                for i in range(1200)], srt)
    t0 = time.perf_counter()
    ed = editor.open_editor(root, os.path.join(TMP, "missing.mp4"), srt)
    check(time.perf_counter() - t0 < 5, "1200 cues open quickly")
    pump(root, 0.3)
    check("not found" in ed.preview.cget("text"), "missing video shown in preview")

    ed.select(5)
    ed.win.focus_force()
    ed.text_box.focus_force()
    pump(root, 0.2)
    ed.text_box.mark_set("insert", "1.0")
    ed.text_box.event_generate("<Delete>")
    ed._on_text_edit()
    check(len(ed.cues) == 1200, "Del while typing never deletes a cue")
    if ed.win.focus_get() is ed.text_box:      # Windows may refuse focus to a background app
        check(ed.cues[5].text == "ümle 5", "Del while typing edits the text")
    t0 = time.perf_counter()
    for _ in range(10):
        ed.text_box.insert("end", "x")
        ed._on_text_edit()
    check((time.perf_counter() - t0) / 10 < 0.03, "typing stays fast with 1200 cues")

    ed.select(0)
    ed.delete_cue()
    ed.select(9)
    ed.text_box.insert("end", " typed")
    ed._on_text_edit()
    ed.undo()
    check(len(ed.cues) == 1199 and not ed.cues[9].text.endswith("typed"), "Undo reverts typing first")
    ed.undo()
    check(len(ed.cues) == 1200, "second Undo restores the deleted cue")

    ed.select(len(ed.cues) - 1)
    ed.merge_with_next()
    check("last cue" in ed.status_var.get(), "merge at the last cue explained")
    ed.split_cue()
    check(len(ed.cues) == 1201, "split the last cue")

    ed.start_var.set("nan")
    check(not ed._apply_times(show_errors=True), "time 'nan' rejected")
    total, _ = ed.replace_all("cümle 1(", "X")
    check(total == 0, "special characters are searched literally")
    expected = sum(c.text.count("cümle 11") for c in ed.cues)
    total, _ = ed.replace_all("CÜMLE 11", "Cümle on bir")
    check(total == expected > 0, f"case-insensitive replace with Turkish letters: {total}")

    ANSWERS["askyesnocancel"] = None
    check(ed.close() is False and not ed.closed, "Cancel at 'Save changes?' keeps the editor")
    ANSWERS["askyesnocancel"] = True
    check(ed.close() is True and ed.closed, "Yes saves and closes")
    ANSWERS.pop("askyesnocancel")
    check(os.path.isfile(srt + ".bak") and len(editor.subtitles.read_srt(srt)) == 1201,
          "saved, original kept as .bak")
    root.destroy()


def main() -> int:
    editor.enable_dpi_awareness()
    tests = [test_strings, test_parse_time, test_fonts, test_paths, test_settings]
    for lang in LANGS:
        tests += [lambda lang=lang: test_layout(lang), lambda lang=lang: test_add_and_drop(lang),
                  lambda lang=lang: test_batch(lang)]
    tests += [test_language_switch, test_review_flow, test_editor]
    names = ["test_strings", "test_parse_time", "test_fonts", "test_paths", "test_settings"]
    names += [f"{n} [{lang}]" for lang in LANGS for n in ("test_layout", "test_add_and_drop", "test_batch")]
    names += ["test_language_switch", "test_review_flow", "test_editor"]
    try:
        for name, test in zip(names, tests):
            print("==", name)
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
