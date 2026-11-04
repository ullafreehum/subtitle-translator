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
from tkinter import font as tkfont, messagebox  # noqa: E402

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
editor.get_transcript = lambda: fake_engine
# Never shut the PC down: the command is replaced twice over (harmless + recorded).
SHUTDOWNS: list = []
app.SHUTDOWN_COMMAND = [sys.executable, "-c", "pass"]
app.run_shutdown = lambda: SHUTDOWNS.append(time.time())
# Video lengths by file name (ffprobe is not run on the empty test files).
DURATIONS: dict = {}
app.probe_duration = lambda path: DURATIONS.get(os.path.basename(path))
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
    try:
        engine_translators = _literal("translation.py", "TRANSLATORS")
    except (KeyError, ValueError):
        engine_translators = {}
        print("WARN: translation.TRANSLATORS is not a plain dict: names not compared")
    ids = set(engine_translators.values()) | {"nllb", "nllb_large", "online"}
    check(all("translator_" + i in i18n_app.STRINGS for i in ids), f"translator names: {ids}")
    # English texts of the translators stay the engine's reviewed display names.
    for name, tid in engine_translators.items():
        same = i18n_app.STRINGS.get("translator_" + tid, {}).get("en") == name
        if tid in ("nllb", "online"):
            check(same, f"English name of {tid}")
        elif not same:
            print(f"WARN: English name of {tid} differs from translation.py: {name!r}")
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
        "clean": a.clean_audio_var.get(), "retime": a.retime_var.get(),
        "export": a._export_formats(), "shutdown": a.shutdown_var.get(),
        "advanced": a._advanced_open,
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
    a.clean_audio_var.set(True)
    a.export_vars["txt"].set(True)
    a.shutdown_var.set(True)
    a._toggle_advanced()
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

    check(a.advanced.winfo_ismapped(), "switch keeps the advanced options open")
    a.shutdown_var.set(False)

    # While videos are processed: the window stays as it is until the batch ends.
    fake_engine.STEP_DELAY = 0.1
    a.burn_var.set(False)
    a.start()
    check(wait(root, lambda: a._current_iid is not None, 60), "switch: batch running")
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
    check(wait(root, lambda: a._current_iid is not None, 60), "switch: second batch running")
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


# ---------------------------------------------------------------- translators, new options

def test_translators() -> None:
    """The translator list comes from available_translators(): the large NLLB model only
    when installed; names in the window's language; a saved large model that is gone
    falls back to the normal NLLB model."""
    try:
        for lang in LANGS:
            fake_engine.LARGE_INSTALLED = False
            root, a = new_app({"translator": "nllb_large"}, lang)
            check(a.translator_ids == ["nllb", "online"], f"[{lang}] no large model: {a.translator_ids}")
            check(a._translator_id() == "nllb" and a.translator_var.get() == t("translator_nllb"),
                  f"[{lang}] saved large model falls back to NLLB: {a.translator_var.get()!r}")
            a._on_close()
            check(saved_settings()["translator"] == "nllb", f"[{lang}] fallback saved as nllb")

            fake_engine.LARGE_INSTALLED = True
            root, a = new_app({"translator": "nllb_large"}, lang)
            names = list(a._translator_by_name)
            check(a.translator_ids == ["nllb", "nllb_large", "online"], f"[{lang}] ids {a.translator_ids}")
            check(names == [t("translator_nllb"), t("translator_nllb_large"), t("translator_online")],
                  f"[{lang}] localized by id: {names}")
            check(a._translator_id() == "nllb_large"
                  and a.translator_var.get() == t("translator_nllb_large"),
                  f"[{lang}] large model kept: {a.translator_var.get()!r}")
            combo = next(w for w in a.inputs if isinstance(w, app.ttk.Combobox)
                         and str(w.cget("textvariable")) == str(a.translator_var))
            text_px = tkfont.nametofont("TkTextFont", root=root).measure(t("translator_nllb_large"))
            check(combo.winfo_reqwidth() > text_px,
                  f"[{lang}] translator box wide enough for {t('translator_nllb_large')!r}")
            check_texts(a, lang)
            a._on_close()
            check(saved_settings()["translator"] == "nllb_large", f"[{lang}] saved by id")
        i18n.set_language("tr")
        check(t("translator_nllb_large") == "Çevrimdışı – NLLB büyük model (en iyi kalite, daha yavaş)",
              "Turkish name of the large model")
        # The id survives a switch of the interface language.
        root, a = new_app({"translator": "nllb_large"}, "tr")
        _invoke_language(a, "English")
        pump(root, 0.1)
        check(a.translator_var.get() == "Offline – NLLB large model (best quality, slower)",
              f"switch: large model in English: {a.translator_var.get()!r}")
        root.destroy()
    finally:
        fake_engine.LARGE_INSTALLED = False


def test_options() -> None:
    """Clean-up, transcript and timing options: defaults, saved, passed to the engine."""
    root, a = new_app({}, "tr")
    check((a.clean_audio_var.get(), a.retime_var.get(), a._export_formats(), a.shutdown_var.get())
          == (False, True, (), False), "option defaults")
    check(not a.advanced.winfo_ismapped() and a.advanced_btn.cget("text") == "▸ Gelişmiş",
          f"advanced options folded away: {a.advanced_btn.cget('text')!r}")
    texts = visible_texts(a)
    for want in ("Konuşmayı temizle (yankılı/gürültülü salonlar için)", "Metin dökümünü de kaydet:",
                 "Word", "Metin", "Çevirileri tam cümle olarak zamanla", "İş bitince bilgisayarı kapat"):
        check(want in texts, f"option shown: {want!r}")
    a.advanced_btn.invoke()
    pump(root, 0.1)
    check(a.advanced.winfo_ismapped() and a.advanced_btn.cget("text") == "▾ Gelişmiş", "advanced opens")
    a.clean_audio_var.set(True)
    a.retime_var.set(False)
    a.export_vars["docx"].set(True)
    a.export_vars["txt"].set(True)
    a.shutdown_var.set(True)
    a._on_close()
    s = saved_settings()
    check((s.get("clean_audio"), s.get("retime_translation"), s.get("export_formats"))
          == (True, False, ["docx", "txt"]), f"options saved: {s}")
    check("shutdown" not in json.dumps(s), "shutdown is never saved")
    root, a = new_app()
    check((a.clean_audio_var.get(), a.retime_var.get(), a._export_formats(), a.shutdown_var.get())
          == (True, False, ("docx", "txt"), False), "options persist, shutdown does not")
    pump(root, 0.1)
    check(a.advanced.winfo_ismapped(), "a changed advanced option is shown")
    root.destroy()
    for bad in ({"clean_audio": "yes", "retime_translation": 0, "export_formats": "docx"},
                {"export_formats": ["pdf", 3, "txt"]}):
        root, a = new_app(bad)
        check(a.clean_audio_var.get() is False and a.retime_var.get() is True
              and a._export_formats() in ((), ("txt",)), f"odd option values ignored: {bad}")
        root.destroy()

    # The options reach process_video; transcripts are listed in the Result column and log.
    out = os.path.join(TMP, "out_options")
    root, a = new_app({"target_langs": ["tr"], "output_dir": out, "clean_audio": True,
                       "retime_translation": False, "export_formats": ["docx", "txt"]}, "en")
    a.add_paths([make_video("options talk.mp4")])
    fake_engine.calls.clear()
    a.start()
    check(wait(root, lambda: not a.running and a.worker is None, 60), "options batch finishes")
    pump(root, 0.2)
    opts = fake_engine.calls[0][3]
    check((opts["clean_audio"], opts["retime_translation"], opts["export_formats"])
          == (True, False, ("docx", "txt")), f"options passed: {opts}")
    iid = next(iter(a.items))
    check("transcript: Word, Text" in a.tree.set(iid, "result"),
          f"Result column lists transcripts: {a.tree.set(iid, 'result')!r}")
    log = a.log_text.get("1.0", "end")
    for lang in ("en", "tr"):
        for fmt in ("docx", "txt"):
            path = os.path.join(out, f"options talk.{lang}.transcript.{fmt}")
            check(t("log_transcript", lang=a._lang_name(lang), path=path) in log,
                  f"log lists {os.path.basename(path)}")
    check(i18n.engine_message("Extracting audio with ffmpeg (with noise and echo reduction)...")
          in log, "clean-up step logged")
    a._phase_from_log("Extracting audio with ffmpeg (with noise and echo reduction)...")
    check(a._phase == "phase_clean_audio", f"clean-up step named in the status line: {a._phase}")
    a._phase = ""
    _invoke_language(a, "Türkçe")
    pump(root, 0.1)
    check("metin dökümü: Word, Metin" in a.tree.set(iid, "result"),
          f"[tr] Result column: {a.tree.set(iid, 'result')!r}")

    # An older engine without the new options: they are left out (and the user told).
    real = fake_engine.process_video

    def old_process_video(video_path, target_langs, source_lang=None, model_size="x",
                          translator="nllb", burn=False, burn_style=None, output_dir=None,
                          glossary_path=None, log=print, progress=lambda p: None, cancel=None):
        return real(video_path, target_langs, source_lang, model_size, translator, burn,
                    burn_style, output_dir, glossary_path, log, progress, cancel)

    fake_engine.process_video = old_process_video
    try:
        a.items[iid].status = app.WAITING
        a.log_text.configure(state="normal")
        a.log_text.delete("1.0", "end")
        a.log_text.configure(state="disabled")
        a.start()
        check(wait(root, lambda: not a.running and a.worker is None, 60), "old engine batch finishes")
        pump(root, 0.2)
        check(a.items[iid].status == app.DONE, f"old engine: done ({a.items[iid].error})")
        log = a.log_text.get("1.0", "end")
        check(t("log_option_unsupported", options="")[:20] in log and t("check_retime") in log,
              f"old engine: ignored options explained: {log[:300]!r}")
    finally:
        fake_engine.process_video = real
    check(app.supported_kwargs(lambda x, **kw: None, {"a": 1}) == {"a": 1}, "**kwargs accepts all")
    check(app.supported_kwargs(lambda x, a=1: None, {"a": 2, "b": 3}) == {"a": 2},
          "unknown kwargs dropped")
    root.destroy()


def test_min_size_layout() -> None:
    """At the minimum window size every option, button and checkbox is shown in full,
    with the advanced options open and the longest translator name, in both languages."""
    for lang in LANGS:
        fake_engine.LARGE_INSTALLED = True
        root, a = new_app({"retime_translation": False, "translator": "nllb_large"}, lang)
        fake_engine.LARGE_INSTALLED = False
        min_w, min_h = root.minsize()
        root.geometry(f"{min_w}x{min_h}")
        pump(root, 0.4)
        clipped = []

        def walk(w):
            for child in w.winfo_children():
                if isinstance(child, (app.ttk.Button, app.ttk.Checkbutton, app.ttk.Combobox)) or (
                        isinstance(child, app.ttk.Label) and child.cget("text")):
                    if not child.winfo_ismapped() or child.winfo_width() < child.winfo_reqwidth() - 1:
                        clipped.append((str(child.cget("text")), child.winfo_width(),
                                        child.winfo_reqwidth(), child.winfo_ismapped()))
                walk(child)

        walk(a.main)
        check(not clipped, f"[{lang}] cut off at minimum size {min_w}x{min_h}: {clipped}")
        rows = a.tree.winfo_height(), a.log_text.winfo_height()
        check(rows[0] > 60 * a.scale and rows[1] > 40 * a.scale,
              f"[{lang}] list and log still usable at minimum size: {rows}")
        print(f"   [{lang}] minimum size {min_w}x{min_h} (scale {a.scale:.2f}), list/log {rows}")
        root.destroy()


# ---------------------------------------------------------------- time left

def test_eta() -> None:
    for lang, expect in (("tr", ["1 dakikadan az kaldı", "yaklaşık 1 dk kaldı", "yaklaşık 12 dk kaldı",
                                 "yaklaşık 1 sa kaldı", "yaklaşık 1 sa 25 dk kaldı", "<1 dk", "~12 dk",
                                 "~2 sa 5 dk"]),
                         ("en", ["less than a minute left", "about 1 min left", "about 12 min left",
                                 "about 1 h left", "about 1 h 25 min left", "<1 min", "~12 min",
                                 "~2 h 5 min"])):
        i18n.set_language(lang)
        got = [app.format_eta(s) for s in (30, 70, 12 * 60 + 10, 3600 + 100, 85 * 60 + 40)]
        got += [app.format_eta(s, short=True) for s in (59, 12 * 60, 125 * 60)]
        check(got == expect, f"[{lang}] format_eta: {got}")

    est = app.EtaEstimator(now=0.0)
    for sec in range(0, 19):
        est.update(sec / 200, now=float(sec))            # 0.5 % per second
    check(est.remaining(now=18.0) is None, "nothing before 20 s")
    slow = app.EtaEstimator(now=0.0)
    slow.update(0.03, now=40.0)
    check(slow.remaining(now=40.0) is None, "nothing before 5 %")
    for sec in range(19, 41):
        est.update(sec / 200, now=float(sec))
    left = est.remaining(now=40.0)
    check(left is not None and abs(left - 160) < 5, f"steady speed: 160 s left, got {left}")
    est.update(0.21, now=42.0)
    later = est.remaining(now=42.0)
    check(later is not None and abs(later - 158) < 5, f"counts down smoothly: {later}")
    # A sudden jump (a resumed transcription) does not make the estimate collapse.
    est.update(0.6, now=43.0)
    after_jump = est.remaining(now=44.0)
    check(after_jump is not None and after_jump > 100, f"jump restarts the measurement: {after_jump}")
    # Batch: waiting videos by their length, else by the average time per video.
    check(app.batch_remaining(None, 30, 600, [600], []) is None, "no batch estimate before the video's")
    check(app.batch_remaining(100, 200, 600, [], []) == 100, "last video: its own time")
    check(abs(app.batch_remaining(100, 200, 600, [1200, 300], []) - (100 + 1200 * 0.5 + 300 * 0.5)) < 1e-6,
          "by length")
    check(abs(app.batch_remaining(100, 200, None, [None, None], [(500, None)]) - (100 + 2 * 400)) < 1e-6,
          "by average")
    check(abs(app.batch_remaining(60, 60, None, [1000], [(600, 1200)]) - (60 + 500)) < 1e-6,
          "length ratio from finished videos")

    # In the window: Status column, status line and the batch label.
    real = (app.EtaEstimator.MIN_SECONDS, app.EtaEstimator.MIN_SPAN)
    app.EtaEstimator.MIN_SECONDS, app.EtaEstimator.MIN_SPAN = 0.3, 0.3
    DURATIONS.update({"eta one.mp4": 60.0, "eta two.mp4": 120.0})
    fake_engine.STEP_DELAY = 0.15
    try:
        for lang in LANGS:
            root, a = new_app({"target_langs": ["tr"], "output_dir": os.path.join(TMP, "out_eta")}, lang)
            a.add_paths([make_video("eta one.mp4"), make_video("eta two.mp4")])
            pump(root, 0.2)
            a.start()
            seen = {"column": "", "line": "", "batch": ""}

            def look():
                iid = a._current_iid
                if iid and a.items[iid].eta is not None:
                    seen["column"] = a.tree.set(iid, "status")
                    seen["line"] = a.status_var.get()
                    seen["batch"] = a.batch_eta_var.get() or seen["batch"]
                return bool(seen["column"] and seen["batch"])

            check(wait(root, look, 30), f"[{lang}] time left shown: {seen}")
            check(" · " in seen["column"] and seen["column"].startswith(t("status_working", pct=0)[:4]),
                  f"[{lang}] Status column: {seen['column']!r}")
            check(t("eta_left", time="")[:5] in seen["line"] or t("eta_less_minute") in seen["line"],
                  f"[{lang}] status line: {seen['line']!r}")
            check(seen["batch"].startswith(t("eta_batch", eta="")), f"[{lang}] batch label: {seen['batch']!r}")
            check(wait(root, lambda: not a.running and a.worker is None, 60), f"[{lang}] eta batch finishes")
            pump(root, 0.2)
            check(a.batch_eta_var.get() == "" and all(i.eta is None for i in a.items.values()),
                  f"[{lang}] time left cleared at the end")
            check(len(a._run_times) == 2 and a._run_times[0][1] == 60.0,
                  f"[{lang}] times recorded: {a._run_times}")
            check(a.items[next(iter(a.items))].result.get("audio_duration") == 12.0, "fake length")
            root.destroy()
        # ffprobe failed: the engine's "audio_duration" is used for the next estimates.
        root, a = new_app({"target_langs": ["tr"], "output_dir": os.path.join(TMP, "out_eta")}, "en")
        fake_engine.STEP_DELAY = 0.01
        a.add_paths([make_video("eta three.mp4")])
        a.start()
        check(wait(root, lambda: not a.running and a.worker is None, 60), "eta fallback batch finishes")
        pump(root, 0.2)
        check(a._run_times and a._run_times[-1][1] == 12.0, f"engine length used: {a._run_times}")
        root.destroy()
    finally:
        app.EtaEstimator.MIN_SECONDS, app.EtaEstimator.MIN_SPAN = real
        fake_engine.STEP_DELAY = 0.01
        DURATIONS.clear()


# ---------------------------------------------------------------- shut down when finished

def _rerun(a) -> None:
    for item in a.items.values():
        item.status = app.WAITING
    a.start()


def test_shutdown() -> None:
    """Countdown after the batch (also with failures), Cancel / Shut down now, never after
    the user cancelled. run_shutdown is replaced by a recorder (see the top of the file)."""
    real_countdown = app.SHUTDOWN_COUNTDOWN
    app.SHUTDOWN_COUNTDOWN = 2
    logs = os.path.join(TMP, "logs")
    try:
        for lang in LANGS:
            out = os.path.join(TMP, "out_shutdown_" + lang)
            root, a = new_app({"target_langs": ["tr"], "output_dir": out}, lang)
            good, bad = make_video(f"sd good {lang}.mp4"), make_video(f"sd bad {lang}.mp4")
            fake_engine.FAIL_NAMES.add(os.path.basename(bad))
            a.add_paths([good, bad])
            SHUTDOWNS.clear()
            DIALOGS.clear()
            a.start()
            a.shutdown_var.set(True)                  # ticked while the batch runs
            check(wait(root, lambda: not a.running and a.worker is None, 60), f"[{lang}] batch ends")
            pump(root, 0.1)
            dlg = a._shutdown_dialog
            check(dlg is not None and dlg.winfo_exists(), f"[{lang}] countdown shown (one video failed)")
            check(not any(k == "showwarning" for k, _ in DIALOGS), f"[{lang}] no popup waits for a click")
            if dlg is not None:
                check(dlg.title() == t("shutdown_title") and dlg.now_btn.cget("text") == t("shutdown_now")
                      and dlg.cancel_btn.cget("text") == t("btn_cancel"), f"[{lang}] countdown texts")
                check(dlg.left in (1, 2) and dlg.text.cget("text")
                      == t("shutdown_text", summary=a._summary(a._run_counts), n=dlg.left),
                      f"[{lang}] countdown message: {dlg.text.cget('text')!r}")
                check(t("count_failed", n=1) in dlg.text.cget("text"), f"[{lang}] failures mentioned")
            check(not SHUTDOWNS, f"[{lang}] not before the countdown ends")
            check(wait(root, lambda: SHUTDOWNS, 10), f"[{lang}] shuts down after the countdown")
            saved = sorted(os.listdir(logs)) if os.path.isdir(logs) else []
            check(saved, f"[{lang}] log saved next to settings.json before shutting down")
            if saved:
                with open(os.path.join(logs, saved[-1]), encoding="utf-8") as f:
                    text = f.read()
                check(os.path.basename(bad) in text and t("log_shutdown") in text, f"[{lang}] log content")
            check(saved_settings().get("output_dir") == out, f"[{lang}] settings saved")
            check(not os.path.exists(os.path.join(os.path.dirname(good), "logs")),
                  f"[{lang}] nothing written next to the videos")
            fake_engine.FAIL_NAMES.clear()

            # Cancel in the countdown: no shutdown, the box is unticked.
            a.shutdown_var.set(True)
            SHUTDOWNS.clear()
            _rerun(a)
            check(wait(root, lambda: a._shutdown_dialog is not None, 60), f"[{lang}] countdown again")
            a._shutdown_dialog.cancel_btn.invoke()
            pump(root, 2.5)
            check(not SHUTDOWNS and not a.shutdown_var.get() and a._shutdown_dialog is None,
                  f"[{lang}] Cancel stops the shutdown")
            check(t("log_shutdown_cancelled") in a.log_text.get("1.0", "end"), f"[{lang}] cancel logged")

            # "Shut down now" does not wait for the 60 seconds.
            app.SHUTDOWN_COUNTDOWN = 60
            a.shutdown_var.set(True)
            _rerun(a)
            check(wait(root, lambda: a._shutdown_dialog is not None, 60), f"[{lang}] countdown (60 s)")
            sd = a._shutdown_dialog       # a slow PC may already have ticked once or twice
            check(sd.bar["maximum"] == 60 and sd.left >= 55 and str(sd.left) in sd.text.cget("text"),
                  f"[{lang}] 60 seconds shown: {sd.text.cget('text')!r}")
            a._shutdown_dialog.now_btn.invoke()
            check(len(SHUTDOWNS) == 1 and a._shutdown_dialog is None, f"[{lang}] Shut down now")
            app.SHUTDOWN_COUNTDOWN = 2

            # Cancelled by the user: no countdown.
            a.shutdown_var.set(True)
            SHUTDOWNS.clear()
            fake_engine.STEP_DELAY = 0.2
            _rerun(a)
            wait(root, lambda: a._current_iid is not None, 60)
            a.cancel()
            check(wait(root, lambda: not a.running and a.worker is None, 30), f"[{lang}] cancelled")
            pump(root, 2.5)
            check(a._shutdown_dialog is None and not SHUTDOWNS, f"[{lang}] no shutdown after Cancel")
            fake_engine.STEP_DELAY = 0.01

            # A failing shutdown command is reported.
            def broken():
                raise FileNotFoundError(2, "The system cannot find the file specified", "shutdown")

            app.run_shutdown = broken
            DIALOGS.clear()
            a._shutdown_now()
            check(DIALOGS and DIALOGS[-1][0] == "showerror"
                  and DIALOGS[-1][1].startswith(t("shutdown_failed", error="").strip()),
                  f"[{lang}] failed shutdown explained: {DIALOGS}")
            app.run_shutdown = lambda: SHUTDOWNS.append(time.time())
            a.shutdown_var.set(False)
            a._on_close()
            shutil.rmtree(logs, ignore_errors=True)
    finally:
        app.SHUTDOWN_COUNTDOWN = real_countdown
        app.run_shutdown = lambda: SHUTDOWNS.append(time.time())
        fake_engine.FAIL_NAMES.clear()
        fake_engine.STEP_DELAY = 0.01


# ---------------------------------------------------------------- transcript from the File menu

def test_make_transcript() -> None:
    for lang in LANGS:
        root, a = new_app({}, lang)
        labels = menu_labels(a.menubar)
        check(t("menu_make_transcript") in labels, f"[{lang}] File menu entry: {labels}")
        srt = os.path.join(TMP, f"menu talk {lang}.tr.srt")
        editor.subtitles.write_srt([editor.subtitles.Cue(1.0, 3.0, "Merhaba dünya")], srt)
        out = os.path.join(TMP, f"menu talk {lang}.tr.docx")
        real_open, real_save = app.filedialog.askopenfilename, editor.filedialog.asksaveasfilename
        app.filedialog.askopenfilename = lambda **kw: srt
        editor.filedialog.asksaveasfilename = lambda **kw: out
        editor._transcript_choice.update(fmt="docx", timestamps=False)
        fake_engine.transcript_calls.clear()
        ANSWERS["askyesno"] = False
        try:
            dlg = a.make_transcript()
            pump(root, 0.1)
            check(dlg is not None and dlg.title() == t("ed_transcript_title"), f"[{lang}] dialog opens")
            check(dlg is not None and dlg.export() == out, f"[{lang}] exported")
            check(fake_engine.transcript_calls == [(srt, out, "docx", False)],
                  f"[{lang}] export_srt_transcript called: {fake_engine.transcript_calls}")
            check(t("log_transcript_saved", path=out) in a.log_text.get("1.0", "end"), f"[{lang}] logged")
            app.filedialog.askopenfilename = lambda **kw: ""
            check(a.make_transcript() is None, f"[{lang}] no SRT chosen: nothing happens")
        finally:
            app.filedialog.askopenfilename, editor.filedialog.asksaveasfilename = real_open, real_save
            ANSWERS.pop("askyesno", None)
        root.destroy()


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
    extra = [test_language_switch, test_translators, test_options, test_min_size_layout, test_eta,
             test_shutdown, test_make_transcript, test_review_flow, test_editor]
    tests += extra
    names = ["test_strings", "test_parse_time", "test_fonts", "test_paths", "test_settings"]
    names += [f"{n} [{lang}]" for lang in LANGS for n in ("test_layout", "test_add_and_drop", "test_batch")]
    names += [f.__name__ for f in extra]
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
