"""Subtitle Translator - main window.

A batch queue of videos is transcribed, translated into one or more languages and
optionally burned into new videos by engine.process_video, one video at a time in a
single background thread. The worker never touches Tk: it only puts messages on
self.queue, which the Tk thread drains with root.after.

The window is bilingual (Turkish by default, English from Settings > Language). Every
text comes from i18n.t() with the keys in i18n_app.py. Switching the language rebuilds
the window's widgets from the current state (queue, options, log); while videos are
being processed the switch waits until the batch has finished.
"""

import collections
import json
import os
import queue
import re
import sys
import tempfile
import threading
import time
import traceback
import tkinter as tk
from dataclasses import dataclass, field
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

APP_NAME = "Subtitle Translator"     # English name (command line, files); windows use t("app_name")
APP_DIR = os.path.dirname(os.path.abspath(__file__))
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")
ICON_PATH = os.path.join(APP_DIR, "assets", "icon.ico")
AUTO = "auto"                        # settings value of "Auto-detect" for the source language
VIDEO_EXTS = (".mp4", ".mkv", ".mov", ".avi", ".webm", ".m4v")
# Videos this program makes (finished / being written): skipped when adding a folder.
OUTPUT_VIDEO_SUFFIXES = (".subtitled.mp4", ".part.mp4")
MAIN_LANGUAGES = ("tr", "en")        # listed first, before the alphabetical rest

# Make sure modules next to this file are importable regardless of cwd.
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import i18n  # noqa: E402
import i18n_app  # noqa: E402,F401  (imported by name so PyInstaller bundles it)
from i18n import t  # noqa: E402

try:  # drag & drop is optional
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:
    TkinterDnD = None
    DND_FILES = None

try:
    import engine
    ENGINE_ERROR = None
except Exception:  # missing dependency etc. - report it in the GUI
    engine = None
    ENGINE_ERROR = traceback.format_exc()

import editor  # noqa: E402  (light imports only; engine is loaded lazily there)

# Queue item states (codes; the Status column shows t("status_" + state)).
WAITING, WORKING, DONE, REVIEW, FAILED, CANCELLED = (
    "waiting", "working", "done", "review", "failed", "cancelled")
FINISHED_STATES = (DONE, FAILED, CANCELLED)


def video_types() -> list[tuple[str, str]]:
    return [(t("filter_videos"), " ".join("*" + e for e in VIDEO_EXTS)), (t("filter_all"), "*.*")]


def srt_types() -> list[tuple[str, str]]:
    return [(t("filter_srt"), "*.srt"), (t("filter_all"), "*.*")]


# ---------------------------------------------------------------- settings

def load_settings() -> dict:
    try:
        with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_settings(data: dict) -> None:
    # Write a temporary file and swap it in, so a crash never leaves half a file.
    tmp = SETTINGS_PATH + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.replace(tmp, SETTINGS_PATH)
    except Exception:
        pass


def _setting(settings: dict, key: str, kind: type, default):
    """A settings value of the expected type (old or hand-edited files may differ)."""
    value = settings.get(key, default)
    return value if isinstance(value, kind) else default


def lang_code(value, languages: dict) -> str | None:
    """Language code for a saved value: a code ("tr"), or the English display name
    ("Turkish") that older versions stored. None if unknown."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    if value in languages.values():
        return value
    for name, code in languages.items():
        if value.casefold() == name.casefold():
            return code
    return None


def translator_id(value, translators: dict, default: str | None) -> str | None:
    """Translator id for a saved value: an id ("nllb"), a display name, or an old
    display name ("Google (online)") that was renamed since."""
    ids = list(dict.fromkeys(translators.values()))
    if not ids:
        return None
    if value in ids:
        return value
    if value in translators:
        return translators[value]
    low = value.lower() if isinstance(value, str) else ""
    for word, tid in (("google", "online"), ("online", "online"), ("nllb", "nllb"),
                      ("offline", "nllb")):
        if word in low and tid in ids:
            return tid
    return default if default in ids else ids[0]


# ---------------------------------------------------------------- helpers

_TR_ALPHABET = "abcçdefgğhıijklmnoöprsştuüvyz"


def sort_key(text: str):
    """Alphabetical order in the current language (Turkish: ç after c, ı before i, ...)."""
    if i18n.language() != "tr":
        return text.casefold()
    low = text.replace("I", "ı").replace("İ", "i").lower()
    return [_TR_ALPHABET.index(c) if c in _TR_ALPHABET else 100 + ord(c) for c in low]


def is_video(path: str) -> bool:
    return os.path.isfile(path) and path.lower().endswith(VIDEO_EXTS)


def is_output_video(name: str) -> bool:
    return name.lower().endswith(OUTPUT_VIDEO_SUFFIXES)


def expand_paths(paths, skipped: list | None = None) -> list[str]:
    """Video files from a mix of files and folders (folders searched recursively,
    without the videos this program made). Other paths are added to `skipped`."""
    videos = []
    for p in paths:
        p = os.path.normpath(p.strip().strip('"'))
        if os.path.isdir(p):
            for folder, dirs, files in os.walk(p):
                dirs.sort()
                videos += [os.path.join(folder, f) for f in sorted(files)
                           if f.lower().endswith(VIDEO_EXTS) and not is_output_video(f)]
        elif is_video(p):
            videos.append(p)
        elif skipped is not None:
            skipped.append(p)
    return videos


def error_info(exc: BaseException) -> tuple[str, dict]:
    """A failure as (key, values), so it can be shown in whatever language the window
    has later (render_error). Safe to call from the worker thread."""
    if isinstance(exc, PermissionError):
        return "err_permission", {}
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return "err_disk_full", {}
    if isinstance(exc, MemoryError):
        return "err_memory", {}
    if isinstance(exc, OSError) and exc.strerror:    # from Windows, not an engine message
        name = os.path.basename(str(exc.filename or "").rstrip("\\/"))
        return "raw", {"text": exc.strerror + (f": {name}" if name else "")}
    text = str(exc).strip()
    if isinstance(exc, (RuntimeError, ValueError, OSError)) and text:
        return "engine", {"text": text.splitlines()[0]}   # engine messages are written for users
    return "err_unexpected", {"name": type(exc).__name__}


def render_error(info: tuple[str, dict]) -> str:
    key, values = info
    if key == "raw":
        return values["text"]
    if key == "engine":
        return i18n.engine_message(values["text"])
    return t(key, **values)


def friendly_error(exc: BaseException) -> str:
    """One short line about a failure for the queue and popups (details go to the log)."""
    return render_error(error_info(exc))


# Engine log lines (English) that start a step -> status-bar text key meanwhile.
PHASES = (
    ("Extracting audio", "phase_audio"),
    ("Downloading the speech recognition model", "phase_download_whisper"),
    ("Loading speech recognition model", "phase_load_whisper"),
    ("Transcribing", "phase_transcribe"),
    ("Translating ", "phase_translate_into"),
    ("Downloading the offline translation model", "phase_download_nllb"),
    ("Loading offline translation model", "phase_load_nllb"),
    ("Burning subtitles", "phase_burn"),
)


def folder_problem(folder: str) -> str | None:
    """Why files cannot be saved in `folder` (created if missing), or None if they can."""
    if os.path.exists(folder) and not os.path.isdir(folder):
        return t("err_not_a_folder")
    try:
        os.makedirs(folder, exist_ok=True)
        with tempfile.TemporaryFile(dir=folder):
            pass
    except OSError as exc:
        return friendly_error(exc)
    return None


def find_srts(video: str, folders) -> list[tuple[str, str]]:
    """(language code, path) of <stem>.<code>.srt files for a video."""
    stem = os.path.splitext(os.path.basename(video))[0]
    found, seen = [], set()
    for folder in folders:
        if not folder or not os.path.isdir(folder):
            continue
        for name in sorted(os.listdir(folder)):
            low = name.lower()
            if low.startswith(stem.lower() + ".") and low.endswith(".srt"):
                path = os.path.normcase(os.path.join(folder, name))
                if path not in seen:
                    seen.add(path)
                    found.append((name[len(stem) + 1:-4], os.path.join(folder, name)))
    return found


def user_guide_path() -> str | None:
    """The user guide in the window's language: README.md (Turkish) or README.en.md
    (English), next to app.py or next to the exe when frozen."""
    folders = [APP_DIR]
    if getattr(sys, "frozen", False):
        folders.append(os.path.dirname(sys.executable))
    names = ["README.en.md", "README.md"] if i18n.language() == "en" else ["README.md", "README.en.md"]
    for name in names:
        for folder in folders:
            path = os.path.join(folder, name)
            if os.path.isfile(path):
                return path
    return None


@dataclass
class QueueItem:
    path: str
    status: str = WAITING
    targets: list = field(default_factory=list)   # language codes (shown while waiting)
    result: dict | None = None       # process_video result (for the editor)
    progress: float = 0.0
    error: tuple | None = None       # error_info() of a failure
    detail: str = ""                 # Languages/Result column as last shown


# ---------------------------------------------------------------- main window

class App:
    def __init__(self, root: tk.Tk, initial_paths=None):
        self.root = root
        self.queue: queue.Queue = queue.Queue()
        self.settings = load_settings()
        # Before any widget: every text is looked up in this language.
        i18n.set_language(_setting(self.settings, "ui_language", str, i18n.DEFAULT))
        self._pending_language: str | None = None   # chosen while a batch runs

        self.items: dict[str, QueueItem] = {}         # Treeview iid -> item (Tk thread only)
        self._pending: collections.deque = collections.deque()   # (iid, path) for the worker
        self._lock = threading.Lock()
        self.worker: threading.Thread | None = None
        self.cancel_event: threading.Event | None = None
        self._run_opts: dict = {}
        self._run_total = 0
        self._run_finished = 0
        self._run_counts: collections.Counter = collections.Counter()
        self._failures: list[tuple[str, tuple]] = []   # (file name, error_info) of this batch
        self._review_run = False
        self._current_iid: str | None = None
        self._next_id = 0
        self.last_output_dir: str | None = None
        self.editors: dict[str, editor.SubtitleEditor] = {}  # srt path -> open editor
        self._closing = False
        self._status_fn = lambda: t("status_ready")    # re-rendered after a language switch
        # Current step of the running video, for the status bar.
        self._phase = ""                    # key in i18n_app, e.g. "phase_transcribe"
        self._phase_kw: dict = {}
        self._phase_detail: tuple | None = None   # (key, n), e.g. ("elapsed_min", 2)
        self._phase_started = 0.0
        self._phase_progress = 0.0          # item progress when the step started
        self._busy_bar = False              # progress bar animating (no measurable progress)

        self.scale = editor.ui_scale(root)
        self._base_min = (820, 640)
        editor.fit_window(root, 940, 780, *self._base_min)
        if os.path.isfile(ICON_PATH):
            try:
                root.iconbitmap(default=ICON_PATH)   # default= also applies to the editor
            except tk.TclError:
                pass
        style = ttk.Style(root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        editor.style_treeview(root)

        self.languages: dict = dict(getattr(engine, "LANGUAGES", {}) or {})
        self.code_to_name = {code: name for name, code in self.languages.items()}  # English
        self.model_sizes = list(getattr(engine, "MODEL_SIZES", [])) or ["large-v3-turbo"]
        self.translators: dict = dict(getattr(engine, "TRANSLATORS", {}) or {})
        self.translator_ids = list(dict.fromkeys(self.translators.values()))

        self._init_vars()
        self._build_all(self._initial_state())
        self._setup_dnd()
        root.protocol("WM_DELETE_WINDOW", self._on_close)

        if ENGINE_ERROR:
            self._log(t("log_engine_failed", details=ENGINE_ERROR))
            messagebox.showerror(t("app_name"), t("engine_missing"))
        if initial_paths:
            self.add_paths(initial_paths)
        self._refresh_empty_hint()
        self.root.after(100, self._poll_queue)

    # ------------------------------------------------------------ variables

    def _init_vars(self) -> None:
        s = self.settings
        default_model = getattr(engine, "DEFAULT_MODEL", self.model_sizes[-1])
        model = _setting(s, "model", str, default_model)
        self.model_var = tk.StringVar(value=model if model in self.model_sizes else
                                      (default_model if default_model in self.model_sizes
                                       else self.model_sizes[-1]))
        self.output_var = tk.StringVar(value=_setting(s, "output_dir", str, ""))
        self.burn_var = tk.BooleanVar(value=_setting(s, "burn", bool, False))
        self.review_var = tk.BooleanVar(value=_setting(s, "review", bool, False))
        self.ui_lang_var = tk.StringVar(value=i18n.language())
        # Texts of these depend on the language: set by _build_widgets.
        self.source_var = tk.StringVar()
        self.translator_var = tk.StringVar()
        self.status_var = tk.StringVar()
        self.targets_var = tk.StringVar()

    def _initial_state(self) -> dict:
        """Choices from settings.json as codes (older files stored English names)."""
        s = self.settings
        source = lang_code(s.get("source_lang"), self.languages)
        saved = s.get("target_langs")
        if not isinstance(saved, list):
            saved = [s.get("target_lang")]          # old single-language setting
        targets = [c for c in (lang_code(v, self.languages) for v in saved) if c]
        if not targets:
            codes = list(self.languages.values())
            targets = ["tr"] if "tr" in codes else codes[:1]
        translator = translator_id(s.get("translator"), self.translators,
                                   getattr(engine, "DEFAULT_TRANSLATOR", None))
        burn_style = s.get("burn_style") if isinstance(s.get("burn_style"), dict) else None
        return {"source": source, "targets": list(dict.fromkeys(targets)),
                "translator": translator, "burn_style": burn_style}

    # ------------------------------------------------------------ names in the current language

    def _lang_name(self, code: str | None) -> str:
        if not code:
            return ""
        if "lang_" + code in i18n_app.STRINGS:
            return t("lang_" + code)
        return self.code_to_name.get(code, code)

    def _translator_name(self, tid: str) -> str:
        if "translator_" + tid in i18n_app.STRINGS:
            return t("translator_" + tid)
        return next((n for n, i in self.translators.items() if i == tid), tid)

    def _build_names(self) -> None:
        """Language and translator lists in the current language."""
        codes = list(self.languages.values())
        main = [c for c in MAIN_LANGUAGES if c in codes]
        rest = sorted((c for c in codes if c not in main), key=lambda c: sort_key(self._lang_name(c)))
        self.lang_codes = main + rest                         # order of the target list
        self.lang_names = [self._lang_name(c) for c in self.lang_codes]
        self._source_by_name = {t("auto_detect"): None}
        self._source_by_name.update(zip(self.lang_names, self.lang_codes))
        self._translator_by_name = {self._translator_name(i): i for i in self.translator_ids}

    # ------------------------------------------------------------ layout

    def _build_all(self, state: dict) -> None:
        self.root.title(t("app_name"))
        self._build_names()
        self._build_menu()
        self._build_widgets(state)
        self._fit_min_size()

    def _build_menu(self) -> None:
        bar = tk.Menu(self.root, tearoff=False)
        file_menu = tk.Menu(bar, tearoff=False)
        file_menu.add_command(label=t("menu_add_videos"), command=self.browse_videos)
        file_menu.add_command(label=t("menu_add_folder"), command=self.browse_folder)
        file_menu.add_command(label=t("menu_open_subtitles"), command=self.open_subtitles_dialog)
        file_menu.add_separator()
        file_menu.add_command(label=t("menu_exit"), command=self._on_close)
        bar.add_cascade(label=t("menu_file"), menu=file_menu)

        settings_menu = tk.Menu(bar, tearoff=False)
        self.lang_menu = tk.Menu(settings_menu, tearoff=False)
        for code, name in i18n.LANGUAGES.items():        # each in its own language
            self.lang_menu.add_radiobutton(label=name, value=code, variable=self.ui_lang_var,
                                           command=self._on_language_selected)
        settings_menu.add_cascade(label=t("menu_language"), menu=self.lang_menu)
        settings_menu.add_separator()
        settings_menu.add_command(label=t("menu_edit_glossary"), command=self.edit_glossary)
        bar.add_cascade(label=t("menu_settings"), menu=settings_menu)

        help_menu = tk.Menu(bar, tearoff=False)
        help_menu.add_command(label=t("menu_user_guide"), command=self.open_user_guide)
        help_menu.add_separator()
        help_menu.add_command(label=t("menu_about"), command=self.show_about)
        bar.add_cascade(label=t("menu_help"), menu=help_menu)

        old = getattr(self, "menubar", None)
        self.root.configure(menu=bar)
        if old is not None:
            old.destroy()
        self.menubar = bar

    def _build_widgets(self, state: dict) -> None:
        main = self.main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)
        main.columnconfigure(0, weight=1)
        self.inputs: list = []           # settings widgets disabled while a batch runs
        self._rows: list = []            # rows whose width decides the minimum window width

        # --- batch queue
        qf = ttk.LabelFrame(main, text=t("frame_videos"), padding=6)
        qf.grid(row=0, column=0, sticky="nsew")
        main.rowconfigure(0, weight=3)
        qf.columnconfigure(0, weight=1)
        qf.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(qf, columns=("file", "status", "result"), show="headings",
                                 selectmode="extended", height=6)
        for col, title, width, stretch in (("file", t("col_file"), 320, True),
                                           ("status", t("col_status"), 170, False),
                                           ("result", t("col_result"), 280, True)):
            self.tree.heading(col, text=title, anchor="w")
            self.tree.column(col, width=int(width * self.scale), minwidth=int(80 * self.scale),
                             stretch=stretch)
        self.tree.tag_configure("done", foreground="#1e7b34")
        self.tree.tag_configure("review", foreground="#1f5fbf")
        self.tree.tag_configure("failed", foreground="#c0392b")
        self.tree.tag_configure("working", font=("Segoe UI", 9, "bold"))
        sb = ttk.Scrollbar(qf, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        sb.grid(row=0, column=1, sticky="ns")
        self.tree.bind("<Double-1>", self._on_double_click)
        self.tree.bind("<Delete>", lambda e: self.remove_selected())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self._update_queue_buttons())

        self.empty_hint = ttk.Label(self.tree, foreground="gray", background="white",
                                    justify="center")

        qbtns = ttk.Frame(qf)
        qbtns.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        for key, cmd in (("btn_add_videos", self.browse_videos),
                         ("btn_add_folder", self.browse_folder),
                         ("btn_remove", self.remove_selected),
                         ("btn_clear_finished", self.clear_finished)):
            ttk.Button(qbtns, text=t(key), command=cmd).pack(side="left", padx=(0, 4))
        ttk.Button(qbtns, text=t("btn_open_subtitles"),
                   command=self.open_subtitles_dialog).pack(side="right")
        self.review_btn = ttk.Button(qbtns, text=t("btn_review"), command=self.review_selected)
        self.review_btn.pack(side="right", padx=4)
        self._rows.append((qbtns, 6))

        # --- settings
        sf = ttk.LabelFrame(main, text=t("frame_settings"), padding=8)
        sf.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        sf.columnconfigure(1, weight=1)
        self._rows.append((sf, 0))

        left = ttk.Frame(sf)
        left.grid(row=0, column=0, sticky="nw")
        left.columnconfigure(1, weight=1)
        r = 0
        ttk.Label(left, text=t("label_source")).grid(row=r, column=0, sticky="w", pady=3)
        source_names = list(self._source_by_name)
        self.source_var.set(source_names[0] if state["source"] not in self.lang_codes
                            else self._lang_name(state["source"]))
        c = ttk.Combobox(left, textvariable=self.source_var, state="readonly",
                         values=source_names, width=24)
        c.grid(row=r, column=1, sticky="w", padx=6, pady=3)
        self.inputs.append(c)
        r += 1
        ttk.Label(left, text=t("label_model")).grid(row=r, column=0, sticky="w", pady=3)
        mf = ttk.Frame(left)
        mf.grid(row=r, column=1, sticky="w", padx=6, pady=3)
        c = ttk.Combobox(mf, textvariable=self.model_var, state="readonly",
                         values=self.model_sizes, width=16)
        c.pack(side="left")
        ttk.Label(mf, text=t("hint_model"), foreground="gray").pack(side="left", padx=6)
        self.inputs.append(c)
        r += 1
        ttk.Label(left, text=t("label_translator")).grid(row=r, column=0, sticky="w", pady=3)
        names = list(self._translator_by_name)
        self.translator_var.set(self._translator_name(state["translator"])
                                if state["translator"] in self.translator_ids
                                else (names[0] if names else ""))
        c = ttk.Combobox(left, textvariable=self.translator_var, state="readonly",
                         values=names, width=38)
        c.grid(row=r, column=1, sticky="w", padx=6, pady=3)
        self.inputs.append(c)
        r += 1
        ttk.Label(left, text=t("label_output")).grid(row=r, column=0, sticky="w", pady=3)
        of = ttk.Frame(left)
        of.grid(row=r, column=1, sticky="ew", padx=6, pady=3)
        e = ttk.Entry(of, textvariable=self.output_var, width=34)
        e.pack(side="left", fill="x", expand=True)
        b = ttk.Button(of, text=t("btn_browse"), command=self.browse_output)
        b.pack(side="left", padx=(4, 0))
        self.inputs += [e, b]
        r += 1
        ttk.Label(left, text=t("hint_output"), foreground="gray").grid(
            row=r, column=1, sticky="w", padx=6)

        right = ttk.Frame(sf)
        right.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        ttk.Label(right, text=t("label_targets")).grid(row=0, column=0, columnspan=2, sticky="w")
        self.target_list = tk.Listbox(right, selectmode="multiple", exportselection=False,
                                      height=6, activestyle="none")
        for name in self.lang_names:
            self.target_list.insert("end", name)
        targets = [c for c in state["targets"] if c in self.lang_codes]
        for code in targets:
            self.target_list.selection_set(self.lang_codes.index(code))
        if targets:
            self.target_list.see(self.lang_codes.index(targets[0]))
        tsb = ttk.Scrollbar(right, orient="vertical", command=self.target_list.yview)
        self.target_list.configure(yscrollcommand=tsb.set)
        self.target_list.grid(row=1, column=0, sticky="nsew", pady=(2, 0))
        tsb.grid(row=1, column=1, sticky="ns", pady=(2, 0))
        self.target_list.bind("<<ListboxSelect>>", lambda e: self._update_targets_label())
        ttk.Label(right, textvariable=self.targets_var, foreground="#1f5fbf").grid(
            row=2, column=0, columnspan=2, sticky="w")
        self._update_targets_label()

        # --- burn options
        bf = ttk.LabelFrame(main, text=t("frame_burn"), padding=8)
        bf.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        cb = ttk.Checkbutton(bf, text=t("check_burn"), variable=self.burn_var,
                             command=self._update_review_check)
        cb.grid(row=0, column=0, sticky="w")
        # Only meaningful with burning: without it you can always review afterwards.
        self.review_check = ttk.Checkbutton(bf, text=t("check_review"), variable=self.review_var)
        self.review_check.grid(row=0, column=1, sticky="w", padx=(24, 0))
        self.inputs.append(cb)
        self.burn_options = editor.BurnOptions(bf, state["burn_style"])
        self.burn_options.frame.grid(row=1, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._rows.append((bf, 0))

        # --- actions
        af = ttk.Frame(main)
        af.grid(row=3, column=0, sticky="ew", pady=(10, 4))
        self.start_btn = ttk.Button(af, text=t("btn_start"), command=self.start)
        self.start_btn.pack(side="left")
        self.cancel_btn = ttk.Button(af, text=t("btn_cancel"), command=self.cancel)
        self.cancel_btn.pack(side="left", padx=6)
        self.cancel_btn.state(["disabled"])
        ttk.Button(af, text=t("btn_edit_glossary"), command=self.edit_glossary).pack(
            side="left", padx=(12, 0))
        ttk.Button(af, text=t("btn_open_output"), command=self.open_output).pack(
            side="left", padx=6)
        self._rows.append((af, 0))
        if ENGINE_ERROR:
            self.start_btn.state(["disabled"])

        # Own row: the current step ("Video 1 of 3: Translating into Turkish… 0:42") is long.
        ttk.Label(main, textvariable=self.status_var).grid(row=4, column=0, sticky="w")
        self.progress = ttk.Progressbar(main, mode="determinate", maximum=100)
        self.progress.grid(row=5, column=0, sticky="ew", pady=4)

        self.log_text = ScrolledText(main, height=8, wrap="word", state="disabled",
                                     font=("Consolas", 9))
        self.log_text.grid(row=6, column=0, sticky="nsew", pady=(4, 0))
        main.rowconfigure(6, weight=2)
        self.status_var.set(self._status_fn())
        self._update_queue_buttons()
        self._update_review_check()

    def _fit_min_size(self) -> None:
        """Minimum window size: the design minimum, or wider if this language's buttons
        and options need it (Turkish texts are longer), never wider than the screen."""
        self.root.update_idletasks()
        need = max((w.winfo_reqwidth() + 2 * pad for w, pad in self._rows), default=0)
        need += 2 * int(10 * self.scale) + 4 * int(self.scale)    # frame padding, borders
        s = self.scale
        max_w = self.root.winfo_screenwidth() - int(40 * s)
        max_h = self.root.winfo_screenheight() - int(90 * s)
        min_w = min(max(int(self._base_min[0] * s), need), max_w)
        min_h = min(int(self._base_min[1] * s), max_h)
        self.root.minsize(min_w, min_h)
        if self.root.state() == "normal" and self.root.winfo_width() > 1 \
                and self.root.winfo_width() < min_w:
            self.root.geometry(f"{min_w}x{max(self.root.winfo_height(), min_h)}")

    def _setup_dnd(self) -> None:
        self.dnd_enabled = False
        if TkinterDnD is None or not hasattr(self.root, "drop_target_register"):
            return
        try:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self._on_drop)
            self._register_dnd_widgets()
            self.dnd_enabled = True
        except Exception as exc:
            self._log(t("log_dnd_unavailable", error=exc))
        self._refresh_empty_hint()

    def _register_dnd_widgets(self) -> None:
        # Child widgets are separate drop targets (the window itself is registered once).
        for widget in (self.tree, self.empty_hint, self.log_text):
            widget.drop_target_register(DND_FILES)
            widget.dnd_bind("<<Drop>>", self._on_drop)

    def _on_drop(self, event):
        paths = self.root.tk.splitlist(event.data)   # handles {braced paths with spaces}
        self.add_paths(paths)
        return event.action

    # ------------------------------------------------------------ language

    def _on_language_selected(self) -> None:
        """Settings > Language: apply now if idle, else when the batch has finished."""
        code = self.ui_lang_var.get()
        if code not in i18n.LANGUAGES:
            return
        self.settings["ui_language"] = code
        self._remember()
        if code == i18n.language():
            self._pending_language = None
            return
        if self.running or self._closing:
            self._pending_language = code
            texts = i18n_app.STRINGS                      # said in the chosen language
            messagebox.showinfo(texts["app_name"][code], texts["language_later"][code])
            return
        self.set_ui_language(code)

    def set_ui_language(self, code: str) -> None:
        """Rebuild the window in another language, keeping everything the user did:
        the video list (statuses and results), all options, the log and the window size."""
        if self.running:
            self._pending_language = code
            return
        self._pending_language = None
        state = self._capture_state()
        i18n.set_language(code)
        self.ui_lang_var.set(i18n.language())
        self.main.destroy()
        self._build_all(state)
        self._restore_state(state)

    def _capture_state(self) -> dict:
        return {
            "source": self._source_code(),
            "targets": self._selected_targets(),
            "translator": self._translator_id(),
            "burn_style": self.burn_options.values(),
            "log": self.log_text.get("1.0", "end-1c"),
            "log_y": self.log_text.yview()[0],
            "tree_y": self.tree.yview()[0],
            "targets_y": self.target_list.yview()[0],
            "selection": self.tree.selection(),
            "focus": self.tree.focus(),
            "progress": self.progress["value"],
            "geometry": self.root.geometry() if self.root.state() == "normal" else None,
        }

    def _restore_state(self, state: dict) -> None:
        for iid, item in self.items.items():
            self.tree.insert("", "end", iid=iid)
            self._render_item(iid)
        if state["selection"]:
            self.tree.selection_set(state["selection"])
        if state["focus"] and self.tree.exists(state["focus"]):
            self.tree.focus(state["focus"])
        self.log_text.configure(state="normal")
        self.log_text.insert("1.0", state["log"])
        self.log_text.configure(state="disabled")
        self.progress["value"] = state["progress"]
        if state["geometry"]:
            self.root.geometry(state["geometry"])
        if getattr(self, "dnd_enabled", False):
            try:
                self._register_dnd_widgets()
            except Exception:
                pass
        self.root.update_idletasks()
        self.tree.yview_moveto(state["tree_y"])
        self.target_list.yview_moveto(state["targets_y"])
        self.log_text.yview_moveto(state["log_y"])
        self._refresh_empty_hint()
        self._update_queue_buttons()
        self._update_review_check()

    def show_about(self) -> None:
        messagebox.showinfo(t("about_title"), t("about_text"))

    def open_user_guide(self) -> None:
        path = user_guide_path()
        if not path:
            messagebox.showerror(t("app_name"), t("guide_missing",
                                                  path=os.path.join(APP_DIR, "README.md")))
            return
        try:
            os.startfile(path)
        except OSError as exc:
            messagebox.showerror(t("app_name"), t("guide_open_failed", error=exc))

    # ------------------------------------------------------------ queue management

    def add_paths(self, paths) -> int:
        paths = [p for p in paths if str(p).strip()]
        skipped: list[str] = []
        videos = expand_paths(paths, skipped)
        known = {os.path.normcase(i.path) for i in self.items.values()}
        added = duplicates = 0
        for path in videos:
            if os.path.normcase(path) in known:
                duplicates += 1
                continue
            known.add(os.path.normcase(path))
            iid = f"item{self._next_id}"
            self._next_id += 1
            self.items[iid] = QueueItem(path=path, targets=self._selected_targets())
            self.tree.insert("", "end", iid=iid)
            self._render_item(iid)
            added += 1
            if self.running:      # joins the running batch
                with self._lock:
                    self._pending.append((iid, path))
                self._run_total += 1
        if added:
            self.settings["last_folder"] = os.path.dirname(videos[0])
            self._log(t("log_added", n=added))
        self._refresh_empty_hint()

        # Tell the user why nothing (or not everything) was added.
        notes = []
        if skipped:
            names = [os.path.basename(p) or p for p in skipped]
            shown = "\n".join("•  " + n for n in names[:5])
            more = t("and_more", n=len(names) - 5) if len(names) > 5 else ""
            notes.append(t("note_not_videos", names=shown + more))
        if duplicates and not added:
            notes.append(t("note_duplicates"))
        if not videos and not skipped and paths:
            notes.append(t("note_no_videos"))
        if notes:
            for note in notes:
                self._log(note.replace("\n", " "))
            supported = t("note_supported", types=", ".join(e[1:] for e in VIDEO_EXTS))
            messagebox.showinfo(t("app_name"), "\n\n".join(notes + [supported]))
        return added

    def remove_selected(self) -> None:
        for iid in self.tree.selection():
            if iid == self._current_iid:
                messagebox.showinfo(t("app_name"), t("remove_running"))
                continue
            with self._lock:
                before = len(self._pending)
                self._pending = collections.deque(p for p in self._pending if p[0] != iid)
                if len(self._pending) != before:
                    self._run_total -= 1
            self.items.pop(iid, None)
            self.tree.delete(iid)
        self._refresh_empty_hint()

    def clear_finished(self) -> None:
        for iid, item in list(self.items.items()):
            if item.status in FINISHED_STATES:
                self.items.pop(iid)
                self.tree.delete(iid)
        self._refresh_empty_hint()

    def _set_item(self, iid: str, status: str | None = None, **changes) -> None:
        """Change a queue item (status, targets, result, error, progress) and show it."""
        item = self.items.get(iid)
        if not item:
            return
        if status is not None:
            item.status = status
        for name, value in changes.items():
            setattr(item, name, value)
        self._render_item(iid)
        self._update_queue_buttons()

    def _status_label(self, item: QueueItem) -> str:
        if item.status == WORKING:
            return t("status_working", pct=int(item.progress * 100))
        return t("status_" + item.status)

    def _item_detail(self, item: QueueItem) -> str:
        if item.status == FAILED and item.error:
            return render_error(item.error)           # the reason, in the wide column
        if item.result is not None:
            return self._describe_result(item.result)
        return ", ".join(self._lang_name(c) for c in item.targets)

    def _render_item(self, iid: str) -> None:
        item = self.items.get(iid)
        if not item or not self.tree.exists(iid):
            return
        item.detail = self._item_detail(item)
        tag = {DONE: "done", REVIEW: "review", FAILED: "failed",
               WORKING: "working"}.get(item.status, "")
        self.tree.item(iid, values=(os.path.basename(item.path), self._status_label(item),
                                    item.detail), tags=(tag,) if tag else ())

    def _refresh_empty_hint(self) -> None:
        if self.items:
            self.empty_hint.place_forget()
            return
        text = t("hint_drop") if getattr(self, "dnd_enabled", False) else t("hint_click_add")
        self.empty_hint.configure(text=text)
        self.empty_hint.place(relx=0.5, rely=0.55, anchor="center")

    def _update_queue_buttons(self) -> None:
        item = self._selected_item()
        ok = bool(item and item.result and item.result.get("translated_srts"))
        self.review_btn.state(["!disabled"] if ok else ["disabled"])

    def _update_review_check(self, running: bool | None = None) -> None:
        running = self.running if running is None else running
        enabled = bool(self.burn_var.get()) and not running
        self.review_check.state(["!disabled"] if enabled else ["disabled"])

    def _selected_item(self) -> QueueItem | None:
        sel = self.tree.selection() or ((self.tree.focus(),) if self.tree.focus() else ())
        return self.items.get(sel[0]) if sel else None

    # ------------------------------------------------------------ settings helpers

    def _selected_targets(self) -> list[str]:
        """Codes of the selected target languages, in list order."""
        return [self.lang_codes[i] for i in self.target_list.curselection()]

    def _source_code(self) -> str | None:
        """Code of the chosen source language; None = auto-detect."""
        return self._source_by_name.get(self.source_var.get())

    def _translator_id(self) -> str | None:
        return self._translator_by_name.get(self.translator_var.get(),
                                            getattr(engine, "DEFAULT_TRANSLATOR", None))

    def _update_targets_label(self) -> None:
        names = [self._lang_name(c) for c in self._selected_targets()]
        if not names:
            self.targets_var.set(t("targets_none"))
        else:
            shown = ", ".join(names[:4]) + (t("targets_more", n=len(names) - 4)
                                            if len(names) > 4 else "")
            self.targets_var.set(t("targets_selected", n=len(names), names=shown))

    def _burn_style(self):
        """engine.BurnStyle from the burn controls (dict if the engine is missing)."""
        return self.burn_options.make_style(engine) if engine else self.burn_options.values()

    def _remember(self) -> None:
        """Save the choices as codes, so they survive a language switch."""
        self.settings.update({
            "ui_language": self.ui_lang_var.get(),     # the latest choice (maybe pending)
            "source_lang": self._source_code() or AUTO,
            "target_langs": self._selected_targets(),
            "model": self.model_var.get(),
            "translator": self._translator_id(),
            "output_dir": self.output_var.get().strip(),
            "burn": bool(self.burn_var.get()),
            "review": bool(self.review_var.get()),
            "burn_style": self.burn_options.values(),
        })
        self.settings.pop("target_lang", None)   # old single-language setting
        save_settings(self.settings)

    def _initial_dir(self) -> str | None:
        folder = _setting(self.settings, "last_folder", str, "")
        return folder if folder and os.path.isdir(folder) else None

    # ------------------------------------------------------------ dialogs / buttons

    def browse_videos(self) -> None:
        paths = filedialog.askopenfilenames(title=t("dlg_add_videos"), filetypes=video_types(),
                                            initialdir=self._initial_dir())
        if paths:
            self.add_paths(paths)

    def browse_folder(self) -> None:
        folder = filedialog.askdirectory(title=t("dlg_add_folder"),
                                         initialdir=self._initial_dir())
        if folder:
            self.add_paths([folder])

    def browse_output(self) -> None:
        path = filedialog.askdirectory(title=t("dlg_output_folder"),
                                       initialdir=self.output_var.get() or self._initial_dir())
        if path:
            self.output_var.set(os.path.normpath(path))

    def edit_glossary(self) -> None:
        try:
            import glossary
            glossary.load_glossary()          # creates glossary.txt from the example if missing
            path = glossary.GLOSSARY_PATH
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as f:
                    f.write(t("glossary_new_file"))
            os.startfile(path)
        except Exception as exc:
            messagebox.showerror(t("app_name"), t("glossary_failed", reason=friendly_error(exc)))

    def open_output(self) -> None:
        folder = None
        item = self._selected_item()
        if item and item.result:
            first = next(iter((item.result.get("translated_srts") or {}).values()), None) \
                or item.result.get("original_srt")
            if first:
                folder = os.path.dirname(os.path.abspath(first))
        folder = folder or self.output_var.get().strip() or self.last_output_dir \
            or (os.path.dirname(item.path) if item else None)
        if folder and os.path.isdir(folder):
            try:
                os.startfile(folder)
            except OSError as exc:
                messagebox.showerror(t("app_name"), t("folder_open_failed", error=exc))
        else:
            messagebox.showinfo(t("app_name"), t("no_output_folder"))

    def _log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", str(text).rstrip("\n") + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _set_status(self, fn) -> None:
        """Status line text from fn() (kept, so a language switch can show it again)."""
        self._status_fn = fn
        self.status_var.set(fn())

    # ------------------------------------------------------------ editor

    def _on_double_click(self, event) -> None:
        iid = self.tree.identify_row(event.y)
        if iid:
            self.tree.selection_set(iid)
            self.review_selected(event)

    def review_selected(self, event=None) -> None:
        sel = self.tree.selection()
        item = self.items.get(sel[0]) if sel else None
        if not item:
            return
        srts = (item.result or {}).get("translated_srts") or {}
        if not srts:
            messagebox.showinfo(t("app_name"), t("no_subtitles_yet"))
            return
        if len(srts) == 1:
            self._open_item_editor(sel[0], next(iter(srts)))
            return
        # Several languages: let the user pick one from a popup menu.
        menu = tk.Menu(self.root, tearoff=False)
        for lang in srts:
            menu.add_command(label=f"{self._lang_name(lang)} ({lang})",
                             command=lambda l=lang, i=sel[0]: self._open_item_editor(i, l))
        x = self.root.winfo_pointerx() if event else self.review_btn.winfo_rootx()
        y = self.root.winfo_pointery() if event else self.review_btn.winfo_rooty()
        menu.tk_popup(x, y)

    def _open_item_editor(self, iid: str, lang: str) -> None:
        item = self.items.get(iid)
        if not item or not item.result:
            return
        srt = item.result["translated_srts"][lang]
        original = item.result.get("original_srt")
        if original and os.path.normcase(os.path.abspath(original)) == \
                os.path.normcase(os.path.abspath(srt)):
            original = None
        self.open_editor(item.path, srt, original,
                         on_burned=lambda path: self._on_item_burned(iid, lang, path))

    def open_editor(self, video, srt, original=None, on_burned=None):
        key = os.path.normcase(os.path.abspath(srt))
        ed = self.editors.get(key)
        if ed and not ed.closed and not ed.closing:
            ed.win.deiconify()
            ed.win.lift()
            return ed
        if not os.path.isfile(srt):
            messagebox.showerror(t("app_name"), t("srt_not_found", path=srt))
            return None

        def burned(path):
            self._log(t("log_burned", path=path))
            self.last_output_dir = os.path.dirname(path)
            if on_burned:
                on_burned(path)

        try:
            ed = editor.open_editor(self.root, video, srt, original_srt=original,
                                    burn_style=self._burn_style(), on_burned=burned,
                                    log=self._log)
        except Exception as exc:
            self._log(traceback.format_exc())
            messagebox.showerror(t("app_name"), t("editor_failed", reason=friendly_error(exc)))
            return None
        ed.on_closed = lambda: self.editors.pop(key, None)
        self.editors[key] = ed
        return ed

    def _on_item_burned(self, iid: str, lang: str, path: str) -> None:
        item = self.items.get(iid)
        if not item or item.result is None:
            return
        burned = item.result.setdefault("burned_videos", {})
        burned[lang] = path
        # "Ready for review" until every language has its video.
        all_done = set(item.result.get("translated_srts") or {}) <= set(burned)
        self._set_item(iid, status=DONE if all_done or item.status != REVIEW else REVIEW)

    def open_subtitles_dialog(self) -> None:
        OpenSubtitlesDialog(self)

    # ------------------------------------------------------------ batch processing

    @property
    def running(self) -> bool:
        return bool(self.worker and self.worker.is_alive())

    def start(self) -> None:
        if engine is None or self.running:
            return
        targets = self._selected_targets()
        if not targets:
            messagebox.showwarning(t("app_name"), t("need_target"))
            return
        # Waiting items plus earlier failures/cancellations (retried).
        jobs = [(iid, item.path) for iid, item in self.items.items()
                if item.status in (WAITING, FAILED, CANCELLED)]
        if not jobs:
            messagebox.showinfo(t("app_name"), t("nothing_waiting"))
            return
        output_dir = self.output_var.get().strip().strip('"') or None
        if output_dir:
            output_dir = os.path.abspath(output_dir)
            problem = folder_problem(output_dir)
            if problem:
                messagebox.showerror(t("app_name"), t("bad_output_folder", folder=output_dir,
                                                      problem=problem))
                return

        self._run_opts = dict(
            target_langs=list(targets),
            source_lang=self._source_code(),
            model_size=self.model_var.get(),
            translator=self._translator_id(),
            burn=bool(self.burn_var.get()) and not self.review_var.get(),
            burn_style=self._burn_style(),
            output_dir=output_dir,
        )
        # Review first: the videos are burned from the editor after checking.
        self._review_run = bool(self.burn_var.get()) and bool(self.review_var.get())
        self._remember()
        self.last_output_dir = output_dir

        for iid, _ in jobs:
            self._set_item(iid, status=WAITING, targets=list(targets), result=None, error=None,
                           progress=0.0)
        with self._lock:
            self._pending = collections.deque(jobs)
        self._run_total, self._run_finished = len(jobs), 0
        self._run_counts = collections.Counter()
        self._failures = []
        self.progress["value"] = 0
        self._set_status(lambda: t("status_starting"))
        self._log(t("log_batch_start", n=len(jobs),
                    langs=", ".join(self._lang_name(c) for c in targets)))
        self._set_running(True)

        self.cancel_event = threading.Event()
        self.worker = threading.Thread(target=self._worker_main,
                                       args=(dict(self._run_opts), self.cancel_event),
                                       daemon=True)
        self.worker.start()

    def _worker_main(self, opts: dict, cancel: threading.Event) -> None:
        """Background thread: processes queued videos one by one."""
        put = self.queue.put
        while not cancel.is_set():
            with self._lock:
                if not self._pending:
                    break
                iid, path = self._pending.popleft()
            put(("item_start", iid))
            try:
                result = engine.process_video(
                    path, opts["target_langs"], source_lang=opts["source_lang"],
                    model_size=opts["model_size"], translator=opts["translator"],
                    burn=opts["burn"], burn_style=opts["burn_style"],
                    output_dir=opts["output_dir"],
                    log=lambda msg: put(("log", str(msg))),
                    progress=lambda p, iid=iid: put(("item_progress", (iid, p))),
                    cancel=cancel)
                put(("item_done", (iid, result)))
            except Exception as exc:
                if isinstance(exc, engine.Cancelled) or cancel.is_set():
                    put(("item_cancelled", iid))
                    break
                put(("item_failed", (iid, error_info(exc), traceback.format_exc())))
        put(("batch_end", None))

    def cancel(self) -> None:
        if self.cancel_event and not self.cancel_event.is_set():
            self.cancel_event.set()
            self._set_status(lambda: t("status_cancelling"))
            self._log(t("log_cancel_requested"))
            self.cancel_btn.state(["disabled"])

    def _set_running(self, running: bool) -> None:
        flag = ["disabled"] if running else ["!disabled"]
        for w in self.inputs:
            w.state(flag)
            if not running and isinstance(w, ttk.Combobox):
                w.state(["readonly"])
        self.target_list.configure(state="disabled" if running else "normal")
        self.burn_options.set_enabled(not running)
        self.start_btn.state(flag)
        self.cancel_btn.state(["!disabled"] if running else ["disabled"])
        if not running:
            self._set_busy_bar(False)
        self._update_review_check(running)

    def _describe_result(self, result: dict) -> str:
        langs = [self._lang_name(c) for c in (result.get("translated_srts") or {})]
        detected = result.get("detected_language")
        text = (f"{self._lang_name(detected)} → " if detected else "") + ", ".join(langs)
        videos = len(result.get("burned_videos") or {})
        if videos:
            text += "  ·  " + (t("result_one_video") if videos == 1
                               else t("result_n_videos", n=videos))
        return text

    def _update_overall(self, current: float = 0.0) -> None:
        total = max(1, self._run_total)
        self.progress["value"] = min(100.0, (self._run_finished + current) / total * 100)

    # ------------------------------------------------------------ current step (status bar)

    def _set_phase(self, key: str, **kw) -> None:
        """A new step started; until its progress moves, the bar animates."""
        item = self.items.get(self._current_iid or "")
        self._phase, self._phase_kw, self._phase_detail = key, kw, None
        self._phase_started = time.monotonic()
        self._phase_progress = item.progress if item else 0.0
        self._set_busy_bar(True)
        self._show_phase()

    def _phase_from_log(self, text: str) -> None:
        """Follow the engine's (English) log lines to name the current step."""
        line = text.strip()
        if line.startswith("still downloading"):    # "... (1.3 GB), 2 min so far. Please wait..."
            m = re.search(r"(\d+) (min|s) so far", line)
            self._phase_detail = (("elapsed_min" if m.group(2) == "min" else "elapsed_sec"),
                                  int(m.group(1))) if m else None
            self._show_phase()
            return
        for prefix, phase in PHASES:
            if line.startswith(prefix):
                if phase == "phase_translate_into":
                    match = re.match(r"Translating \w+ -> ([\w-]+)", line)
                    if not match:
                        return                     # "Translating 13 subtitles (…)"
                    self._set_phase(phase, lang=self._lang_name(match.group(1)))
                else:
                    self._set_phase(phase)
                return

    def _show_phase(self) -> None:
        if not self.running or self._closing or self.cancel_event.is_set():
            return
        n = min(self._run_finished + 1, self._run_total)
        text = t("status_video", n=n, total=self._run_total)
        if self._phase:
            seconds = int(time.monotonic() - self._phase_started)
            text += f": {t(self._phase, **self._phase_kw)}…  {seconds // 60}:{seconds % 60:02d}"
            if self._phase_detail:
                key, value = self._phase_detail
                text += f"  ({t(key, n=value)})"
        self._set_status(lambda: text)

    def _set_busy_bar(self, busy: bool) -> None:
        """Animate the progress bar while a step gives no progress (model loading,
        downloads, the start of speech recognition), so the window never looks frozen."""
        if busy == self._busy_bar:
            return
        self._busy_bar = busy
        if busy:
            self.progress.configure(mode="indeterminate")
            self.progress.start(15)
        else:
            self.progress.stop()
            self.progress.configure(mode="determinate")
            item = self.items.get(self._current_iid or "")
            self._update_overall(item.progress if item else 0.0)

    # ------------------------------------------------------------ queue pump

    def _poll_queue(self) -> None:
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                handler = getattr(self, "_msg_" + kind, None)
                if handler:
                    handler(payload)
        except queue.Empty:
            pass
        if self.running and self._phase:
            self._show_phase()                # keeps the elapsed time ticking
        self.root.after(100, self._poll_queue)

    def _msg_log(self, text) -> None:
        self._log(i18n.engine_message(str(text)))
        self._phase_from_log(str(text))

    def _msg_item_start(self, iid) -> None:
        self._current_iid = iid
        item = self.items.get(iid)
        if item:
            self._log(f"--- {item.path}")
        self._set_item(iid, status=WORKING, progress=0.0)
        self._set_phase("phase_starting")

    def _msg_item_progress(self, payload) -> None:
        iid, p = payload
        try:
            p = max(0.0, min(1.0, float(p)))
        except (TypeError, ValueError):
            return
        item = self.items.get(iid)
        if item:
            changed = int(p * 100) != int(item.progress * 100)
            item.progress = p
            if changed:
                self._render_item(iid)
        if p > self._phase_progress + 0.005:
            self._set_busy_bar(False)         # real progress again
        if not self._busy_bar:
            self._update_overall(p)

    def _msg_item_done(self, payload) -> None:
        iid, result = payload
        result = result or {}
        self._finish_item()
        item = self.items.get(iid)
        if not item:
            return
        status = REVIEW if self._review_run and result.get("translated_srts") else DONE
        self._set_item(iid, status=status, result=result)
        self._run_counts[status] += 1
        if result.get("detected_language"):
            self._log(t("log_detected", lang=self._lang_name(result["detected_language"])))
        if result.get("original_srt"):
            self._log(t("log_original_srt", path=result["original_srt"]))
        for lang, path in (result.get("translated_srts") or {}).items():
            self._log(t("log_srt", lang=self._lang_name(lang), path=path))
        for lang, path in (result.get("burned_videos") or {}).items():
            self._log(t("log_video", lang=self._lang_name(lang), path=path))
        first = next(iter((result.get("translated_srts") or {}).values()), None)
        if first:
            self.last_output_dir = os.path.dirname(os.path.abspath(first))

    def _msg_item_failed(self, payload) -> None:
        iid, info, tb = payload
        self._finish_item()
        self._log(t("log_failed", reason=render_error(info), details=tb))
        item = self.items.get(iid)
        if item:
            self._failures.append((os.path.basename(item.path), info))
        self._set_item(iid, status=FAILED, error=info)
        self._run_counts[FAILED] += 1

    def _msg_item_cancelled(self, iid) -> None:
        self._finish_item()
        self._set_item(iid, status=CANCELLED)
        self._run_counts[CANCELLED] += 1

    def _finish_item(self) -> None:
        self._current_iid = None
        self._run_finished += 1
        self._phase = ""
        self._set_busy_bar(False)
        self._update_overall()

    @staticmethod
    def _summary(counts) -> str:
        parts = [t("count_" + s, n=counts[s]) for s in (DONE, REVIEW, FAILED, CANCELLED)
                 if counts[s]]
        return ", ".join(parts) or t("nothing_processed")

    def _msg_batch_end(self, _payload) -> None:
        self.worker = None
        cancelled = bool(self.cancel_event and self.cancel_event.is_set())
        with self._lock:
            self._pending.clear()     # anything left keeps its "Waiting" status
        self._set_running(False)
        if self._closing:
            return
        counts = collections.Counter(self._run_counts)
        key = "status_batch_cancelled" if cancelled else "status_finished"
        self._set_status(lambda: t(key, summary=self._summary(counts)))
        self._log(t("log_batch_cancelled" if cancelled else "log_batch_finished",
                    summary=self._summary(counts)))
        if not cancelled:
            self.progress["value"] = 100
        if counts[REVIEW]:
            self._log(t("log_review_hint"))
        self.root.bell()
        if self._failures:
            lines = "\n".join(f"•  {name}:\n    {render_error(info)}"
                              for name, info in self._failures[:5])
            if len(self._failures) > 5:
                lines += t("and_more", n=len(self._failures) - 5)
            messagebox.showwarning(t("app_name"), t("batch_failures", n=len(self._failures),
                                                    lines=lines))
        # A language chosen during the batch applies now.
        if self._pending_language and not self.running and not self._closing:
            self.set_ui_language(self._pending_language)

    # ------------------------------------------------------------ closing

    def _on_close(self) -> None:
        if self._closing:
            return
        # Editors first: "Save changes?" -> Cancel keeps everything (batch included) running.
        for ed in list(self.editors.values()):
            if not ed.closed and not ed.close():
                return
        if self.running:
            if not messagebox.askyesno(t("app_name"), t("quit_running")):
                return
            self.cancel()
        self._remember()
        self._closing = True
        self._set_status(lambda: t("status_stopping"))
        for w in (self.start_btn, self.cancel_btn):
            w.state(["disabled"])
        self._quit_when_idle(time.monotonic() + 20)

    def _quit_when_idle(self, deadline: float) -> None:
        """Wait (window responsive) until the worker and any burn have stopped their
        ffmpeg, so nothing keeps running after the window is gone."""
        busy = self.running or any(not ed.closed for ed in self.editors.values())
        if busy and time.monotonic() < deadline:
            self.root.after(100, lambda: self._quit_when_idle(deadline))
            return
        self.root.destroy()


# ---------------------------------------------------------------- open subtitles dialog

class OpenSubtitlesDialog(tk.Toplevel):
    """Pick a video + translated SRT (+ optional original SRT) to open in the editor."""

    def __init__(self, app: App):
        super().__init__(app.root)
        self.app = app
        self.title(t("open_title"))
        self.transient(app.root)
        self.resizable(True, False)
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        self.vars = {}
        rows = (("video", t("open_video"), video_types()),
                ("srt", t("open_srt"), srt_types()),
                ("original", t("open_original"), srt_types()))
        for r, (key, label, types) in enumerate(rows):
            ttk.Label(body, text=label).grid(row=r, column=0, sticky="w", pady=3)
            var = self.vars[key] = tk.StringVar()
            ttk.Entry(body, textvariable=var, width=60).grid(row=r, column=1, sticky="ew",
                                                             padx=6, pady=3)
            ttk.Button(body, text=t("btn_browse"),
                       command=lambda k=key, ft=types: self._browse(k, ft)).grid(row=r, column=2)
        buttons = ttk.Frame(body)
        buttons.grid(row=3, column=0, columnspan=3, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text=t("open_editor"), command=self._ok).pack(side="left", padx=4)
        ttk.Button(buttons, text=t("btn_cancel"), command=self.destroy).pack(side="left")
        self.bind("<Escape>", lambda e: self.destroy())

        # Prefill from the selected queue item.
        item = app._selected_item()
        if item:
            self._set_video(item.path)

    def _browse(self, key: str, types) -> None:
        current = self.vars[key].get() or self.vars["video"].get()
        initial = os.path.dirname(current) if current else self.app._initial_dir()
        path = filedialog.askopenfilename(parent=self, title=t("dlg_choose_file"),
                                          filetypes=types, initialdir=initial)
        if not path:
            return
        path = os.path.normpath(path)
        if key == "video":
            self._set_video(path)
        else:
            self.vars[key].set(path)

    def _set_video(self, video: str) -> None:
        """Set the video and guess its <stem>.<lang>.srt files."""
        self.vars["video"].set(video)
        folders = [self.app.output_var.get().strip(), os.path.dirname(video)]
        found = find_srts(video, folders)
        targets = set(self.app._selected_targets())
        translated = next((p for code, p in found if code in targets), None)
        if not translated and found:
            translated = found[0][1]
        others = [p for code, p in found if p != translated and code not in targets]
        self.vars["srt"].set(translated or "")
        self.vars["original"].set(others[0] if len(others) == 1 else "")

    def _ok(self) -> None:
        video, srt, original = (self.vars[k].get().strip().strip('"')
                                for k in ("video", "srt", "original"))
        if not os.path.isfile(video):
            messagebox.showwarning(t("app_name"), t("open_need_video"), parent=self)
            return
        if not os.path.isfile(srt):
            messagebox.showwarning(t("app_name"), t("open_need_srt"), parent=self)
            return
        if original and not os.path.isfile(original):
            original = None
        self.destroy()
        self.app.open_editor(video, srt, original or None)


def main() -> None:
    editor.ensure_std_streams()      # run.bat starts pythonw: no console
    editor.enable_dpi_awareness()    # before the first window
    root = None
    if TkinterDnD is not None:
        try:
            root = TkinterDnD.Tk()
        except Exception:      # tkdnd library failed to load: run without drag & drop
            root = None
    root = root or tk.Tk()
    App(root, initial_paths=sys.argv[1:])
    root.mainloop()


if __name__ == "__main__":
    main()
