"""Subtitle review/edit window.

open_editor(parent, video_path, translated_srt, original_srt=None, burn_style=None,
            on_burned=None) opens a Toplevel where the user can check every cue against
the original text and a frame of the video, fix wording/timing, save the SRT and
burn a new video.

Standalone:  python editor.py VIDEO TRANSLATED_SRT [ORIGINAL_SRT]

Threading: ffmpeg frame grabs and burning run in worker threads; they only put
messages on self._queue, which the Tk thread drains with after().

Language: every text comes from i18n.t() (table: i18n_editor.py). The editor uses the
language that is current when it opens (the main window sets it); standalone, it
reads "ui_language" from settings.json next to this file.
"""

import copy
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_NAME = "Subtitle Translator"   # English name; windows show app_name()
APP_DIR = os.path.dirname(os.path.abspath(__file__))
ICON_PATH = os.path.join(APP_DIR, "assets", "icon.ico")
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")   # read only (standalone language)

if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

import i18n  # noqa: E402
from i18n import engine_message, t  # noqa: E402

try:
    import subtitles
    SUBTITLES_ERROR = None
except Exception:  # reported when the editor opens
    subtitles = None
    SUBTITLES_ERROR = traceback.format_exc()

_NO_WINDOW = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

# Readability limits (same defaults as subtitles.build_cues).
MAX_CHARS_PER_LINE = 42
MAX_LINES = 2
MAX_CPS = 17.0
PREVIEW_WIDTH = 360
PREVIEW_HEIGHT = 203   # 16:9 box; other aspect ratios are letterboxed inside it

# Burn style choices (BurnStyle values); shown as t("ed_burn_position_<value>") etc.
POSITIONS = ("bottom", "top")
SIZES = ("auto", "small", "medium", "large")
FONTS = ["Arial", "Segoe UI", "Calibri", "Verdana", "Tahoma"]
# A font name goes into ffmpeg's force_style, where , ' : = \ would break the filter.
_SAFE_FONT = re.compile(r"[\w .-]{1,40}")
FFMPEG_MISSING = "ffmpeg-missing"   # marker from the frame worker; shown as t("ed_ffmpeg_missing")


def get_engine():
    """Import engine lazily (it pulls in heavy ML libraries)."""
    import engine
    return engine


# ---------------------------------------------------------------- helpers

def format_time(seconds: float) -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def app_name() -> str:
    """The program's name in the current language (title of windows and message boxes)."""
    return t("ed_app_name")


def format_number(value: float, digits: int = 1) -> str:
    """A decimal number as the user writes it: 17,5 in Turkish, 17.5 in English."""
    text = f"{value:.{digits}f}"
    return text.replace(".", ",") if i18n.language() == "tr" else text


def load_ui_language(path: str | None = None) -> str:
    """"ui_language" from the main window's settings.json (Turkish if missing/invalid).

    Read directly (not through app.py), so standalone mode stays light."""
    try:
        with open(path or SETTINGS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        code = data.get("ui_language") if isinstance(data, dict) else None
    except (OSError, ValueError):
        code = None
    return code if isinstance(code, str) and code in i18n.LANGUAGES else i18n.DEFAULT


def parse_time(text: str) -> float:
    """Parse HH:MM:SS,mmm (also accepts '.', MM:SS or plain seconds)."""
    error = ValueError(t("ed_time_invalid", text=text.strip()))
    parts = text.strip().replace(",", ".").split(":")
    if not 1 <= len(parts) <= 3:
        raise error
    seconds = 0.0
    for part in parts:
        try:
            value = float(part)
        except ValueError:
            raise error from None
        if value < 0 or not math.isfinite(value):   # float() also accepts "nan" and "inf"
            raise error
        seconds = seconds * 60 + value
    return seconds


def flat_text(text: str) -> str:
    """Cue text on one line (write_srt re-wraps it anyway)."""
    return " ".join(text.split())


def readability_issues(text: str, start: float, end: float) -> list[str]:
    """Problems that make a cue hard to read; empty list when fine."""
    issues = []
    flat = flat_text(text)
    duration = end - start
    if duration <= 0:
        issues.append(t("ed_issue_end_before_start"))
    lines = textwrap.wrap(flat, MAX_CHARS_PER_LINE) if flat else []
    if len(lines) > MAX_LINES:
        issues.append(t("ed_issue_too_long", lines=len(lines), width=MAX_CHARS_PER_LINE))
    # Compared as shown (one decimal), so "17.0 chars/s" is never called too fast for 17.
    cps = round(len(flat) / duration, 1) if duration > 0 else 0.0
    if cps > MAX_CPS:
        issues.append(t("ed_issue_too_fast", cps=format_number(cps), max=f"{MAX_CPS:.0f}"))
    if not flat:
        issues.append(t("ed_issue_empty"))
    return issues


def _style_value(style, name: str, default):
    """Read a field from a BurnStyle object or a dict."""
    if style is None:
        return default
    if isinstance(style, dict):
        return style.get(name, default)
    return getattr(style, name, default)


def _clean_font(name) -> str:
    """A font name that is safe to pass to ffmpeg (Arial if not)."""
    name = name.strip() if isinstance(name, str) else ""
    return name if _SAFE_FONT.fullmatch(name) else "Arial"


def open_folder_of(path: str) -> None:
    """Open Explorer with the file selected (or just the folder)."""
    try:
        if sys.platform == "win32" and os.path.isfile(path):
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        else:
            os.startfile(os.path.dirname(path) or ".")
    except OSError as exc:
        messagebox.showerror(app_name(), t("ed_open_folder_failed", error=exc))


def set_window_icon(win) -> None:
    if os.path.isfile(ICON_PATH):
        try:
            win.iconbitmap(ICON_PATH)
        except tk.TclError:
            pass


def enable_dpi_awareness() -> None:
    """Sharp (not stretched and blurry) text at 125 %/150 % Windows scaling.

    Call before the first Tk window. Tk then sizes fonts for the real DPI; pixel sizes
    (window size, column widths, ...) must be multiplied by ui_scale().
    """
    if sys.platform != "win32":
        return
    import ctypes
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)   # system DPI aware
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def ui_scale(widget) -> float:
    """Screen pixels per design pixel: 1.0 at 100 % Windows scaling, 1.5 at 150 %."""
    try:
        return max(1.0, widget.winfo_fpixels("1i") / 96.0)
    except tk.TclError:
        return 1.0


def style_treeview(widget) -> None:
    """Treeview rows tall enough for the font at any Windows scaling (ttk's default is
    a fixed pixel height that clips text at 150 %)."""
    from tkinter import font
    linespace = font.nametofont("TkDefaultFont", root=widget).metrics("linespace")
    ttk.Style(widget).configure("Treeview", rowheight=linespace + int(6 * ui_scale(widget)))


def fit_window(win, width: int, height: int, min_width: int, min_height: int) -> None:
    """Size a window (design pixels) for the screen's scaling, never bigger than the screen."""
    s = ui_scale(win)
    max_w = win.winfo_screenwidth() - int(40 * s)
    max_h = win.winfo_screenheight() - int(90 * s)   # taskbar and title bar
    win.minsize(min(int(min_width * s), max_w), min(int(min_height * s), max_h))
    win.geometry(f"{min(int(width * s), max_w)}x{min(int(height * s), max_h)}")


def stop_process(proc: subprocess.Popen | None) -> None:
    """Stop a helper program and its children ('ffplay' may be a launcher, e.g. a
    Chocolatey shim, whose real ffplay.exe child would keep playing after terminate())."""
    if proc is None or proc.poll() is not None:
        return
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True, creationflags=_NO_WINDOW)
    try:
        proc.kill()
    except OSError:
        pass


# ---------------------------------------------------------------- burn options

class BurnOptions:
    """Position / size / font / background-box controls (main window and editor)."""

    def __init__(self, parent, style=None):
        self.frame = ttk.Frame(parent)
        position = _style_value(style, "position", "bottom")
        size = _style_value(style, "font_size", "auto")
        self._position = position if position in POSITIONS else "bottom"
        self._size = size if size in SIZES else "auto"
        self.position_var = tk.StringVar()
        self.size_var = tk.StringVar()
        font = _clean_font(_style_value(style, "font", "Arial"))
        fonts = FONTS if font in FONTS else FONTS + [font]   # keep a font saved earlier
        self.font_var = tk.StringVar(value=font)
        self.box_var = tk.BooleanVar(value=bool(_style_value(style, "box", False)))

        self.widgets = []
        self._labels = []
        self._combos = []
        for var, values, width in ((self.position_var, [], 8), (self.size_var, [], 8),
                                   (self.font_var, fonts, 11)):
            label = ttk.Label(self.frame)
            label.pack(side="left", padx=(0, 4))
            combo = ttk.Combobox(self.frame, textvariable=var, values=values,
                                 state="readonly", width=width)
            combo.pack(side="left", padx=(0, 12))
            self._labels.append(label)
            self._combos.append(combo)
            self.widgets.append(combo)
        self.box_check = ttk.Checkbutton(self.frame, variable=self.box_var)
        self.box_check.pack(side="left")
        self.widgets.append(self.box_check)
        self.retranslate()
        # Keep the chosen values themselves, so they survive a change of language.
        self.position_var.trace_add("write", lambda *a: self._remember())
        self.size_var.trace_add("write", lambda *a: self._remember())

    def _choices(self) -> tuple[dict, dict]:
        """Display name -> BurnStyle value, in the current language."""
        return ({t(f"ed_burn_position_{v}"): v for v in POSITIONS},
                {t(f"ed_burn_size_{v}"): v for v in SIZES})

    def _remember(self) -> None:
        positions, sizes = self._choices()
        self._position = positions.get(self.position_var.get(), self._position)
        self._size = sizes.get(self.size_var.get(), self._size)

    def retranslate(self) -> None:
        """Show the texts in the current language (keeps the chosen values); the main
        window can call this after switching the language."""
        positions, sizes = self._choices()
        for label, key in zip(self._labels, ("ed_burn_position", "ed_burn_size", "ed_burn_font")):
            label.configure(text=t(key))
        for combo, names in zip(self._combos, (positions, sizes)):
            combo.configure(values=list(names),
                            width=max(8, max(len(n) for n in names) + 1))
        self.position_var.set(t(f"ed_burn_position_{self._position}"))
        self.size_var.set(t(f"ed_burn_size_{self._size}"))
        self.box_check.configure(text=t("ed_burn_box"))

    def values(self) -> dict:
        """Keyword arguments for engine.BurnStyle."""
        positions, sizes = self._choices()
        return {
            "position": positions.get(self.position_var.get(), self._position),
            "font_size": sizes.get(self.size_var.get(), self._size),
            "box": bool(self.box_var.get()),
            "font": _clean_font(self.font_var.get()),
        }

    def make_style(self, engine_module=None):
        """engine.BurnStyle built from the controls (None if the engine is unavailable)."""
        try:
            eng = engine_module or get_engine()
            return eng.BurnStyle(**self.values())
        except Exception:
            return None

    def set_enabled(self, enabled: bool) -> None:
        for w in self.widgets:
            w.state(["!disabled"] if enabled else ["disabled"])
            if enabled and isinstance(w, ttk.Combobox):
                w.state(["readonly"])


# ---------------------------------------------------------------- editor window

class SubtitleEditor:
    """Review/edit window for one translated SRT."""

    def __init__(self, parent, video_path, translated_srt, original_srt=None,
                 burn_style=None, on_burned=None, log=None):
        if subtitles is None:
            raise RuntimeError(t("ed_subtitles_module_failed", details=SUBTITLES_ERROR or ""))
        self.video = os.path.abspath(video_path)
        self.srt_path = os.path.abspath(translated_srt)
        self.original_srt = os.path.abspath(original_srt) if original_srt else None
        self.on_burned = on_burned
        self.on_closed = None             # optional callback (used by standalone mode)
        self._has_log = log is not None
        self.log = log or (lambda text: print(text, file=sys.stderr))   # error details

        self.cues = subtitles.read_srt(self.srt_path)
        self.orig_cues = []
        if self.original_srt and os.path.isfile(self.original_srt):
            try:
                self.orig_cues = subtitles.read_srt(self.original_srt)
            except Exception:
                self.orig_cues = []
        self.has_original = bool(self.orig_cues)
        self.orig_texts = self._match_originals()

        self.current: int | None = None   # index of the cue shown in the detail panel
        self.dirty = False
        self.closed = False
        self.closing = False             # waiting for a cancelled burn to stop, then close
        self._backed_up = False
        self._undo: list = []
        self._edit_undo_for: int | None = None   # cue whose typing already has an undo step
        self._queue: queue.Queue = queue.Queue()
        self._tmpdir = tempfile.mkdtemp(prefix="subtitle_editor_")
        self._frame_cache: dict[float, str | None] = {}   # timestamp -> PNG path (None = failed)
        self._frame_pending: set[float] = set()
        self._wanted_frame: float | None = None
        self._frame_error_logged = False
        self._preview_after = None
        self._preview_image = None
        self._player: subprocess.Popen | None = None
        self._burn_thread: threading.Thread | None = None
        self._burn_cancel: threading.Event | None = None
        self._last_burned: str | None = None
        self._find_dialog = None

        self.win = tk.Toplevel(parent)
        set_window_icon(self.win)
        self.scale = ui_scale(self.win)
        self.preview_size = (int(PREVIEW_WIDTH * self.scale), int(PREVIEW_HEIGHT * self.scale))
        fit_window(self.win, 1060, 780, 860, 620)
        style_treeview(self.win)
        self._build(burn_style)
        self._fill_tree()
        self._update_title()

        self.win.protocol("WM_DELETE_WINDOW", self.close)
        self.win.bind("<Control-s>", lambda e: (self.save(), "break")[1])
        self.win.bind("<Control-S>", lambda e: (self.save(), "break")[1])
        self.win.bind("<Control-f>", lambda e: self.open_find_replace())
        self.win.bind("<Control-Down>", lambda e: self.select_relative(1))
        self.win.bind("<Control-Up>", lambda e: self.select_relative(-1))
        self.win.bind("<F5>", lambda e: self.play_cue())

        if self.cues:
            self.select(0)
        self.win.after(100, self._poll_queue)

    # ------------------------------------------------------------ layout

    def _build(self, burn_style) -> None:
        outer = ttk.Frame(self.win, padding=8)
        outer.pack(fill="both", expand=True)

        info = ttk.Frame(outer)
        info.pack(fill="x")
        # Packed first so a long file path is the part that gets cut off.
        self.flag_label = ttk.Label(info, foreground="#b35c00")
        self.flag_label.pack(side="right")
        ttk.Label(info, text=os.path.basename(self.video),
                  font=("Segoe UI", 10, "bold")).pack(side="left")
        ttk.Label(info, text="   " + self.srt_path, foreground="gray").pack(side="left")

        paned = ttk.Panedwindow(outer, orient="vertical")
        paned.pack(fill="both", expand=True, pady=(6, 0))

        # --- cue list
        list_frame = ttk.Frame(paned)
        columns = ["num", "start", "end"] + (["original"] if self.has_original else []) + ["text"]
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings",
                                 selectmode="browse", height=12)
        headings = {"num": ("ed_col_num", 45, False), "start": ("ed_col_start", 95, False),
                    "end": ("ed_col_end", 95, False), "original": ("ed_col_original", 330, True),
                    "text": ("ed_col_translation", 380, True)}
        for col in columns:
            key, width, stretch = headings[col]
            self.tree.heading(col, text=t(key), anchor="w")
            self.tree.column(col, width=int(width * self.scale), minwidth=int(40 * self.scale),
                             stretch=stretch, anchor="e" if col == "num" else "w")
        self.tree.tag_configure("warn", background="#ffe2b8")
        sb = ttk.Scrollbar(list_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Control-z>", lambda e: self.undo())
        self.tree.bind("<Delete>", lambda e: self.delete_cue())
        paned.add(list_frame, weight=3)

        # --- toolbar + cue details
        bottom = ttk.Frame(paned)
        paned.add(bottom, weight=2)

        bar = ttk.Frame(bottom)
        bar.pack(fill="x", pady=(6, 4))
        for key, cmd in (("ed_btn_previous", lambda: self.select_relative(-1)),
                         ("ed_btn_next", lambda: self.select_relative(1)),
                         ("ed_btn_play", self.play_cue),
                         ("ed_btn_split", self.split_cue),
                         ("ed_btn_merge", self.merge_with_next),
                         ("ed_btn_delete", self.delete_cue),
                         ("ed_btn_undo", self.undo),
                         ("ed_btn_find", self.open_find_replace)):
            ttk.Button(bar, text=t(key), command=cmd).pack(side="left", padx=(0, 4))

        details = ttk.Frame(bottom)
        details.pack(fill="both", expand=True)
        details.columnconfigure(1, weight=1)
        details.rowconfigure(1, weight=1)

        times = ttk.Frame(details)
        times.grid(row=0, column=0, columnspan=2, sticky="w")
        # Fixed width (room for "Cue 9999"), so the fields do not jump between cues.
        self.cue_label = ttk.Label(times, text=t("ed_cue"),
                                   width=max(9, len(t("ed_cue_n", n=9999)) + 1),
                                   font=("Segoe UI", 9, "bold"))
        self.cue_label.pack(side="left")
        self.start_var = tk.StringVar()
        self.end_var = tk.StringVar()
        ttk.Label(times, text=t("ed_start")).pack(side="left")
        self.start_entry = ttk.Entry(times, textvariable=self.start_var, width=13)
        self.start_entry.pack(side="left", padx=(4, 12))
        ttk.Label(times, text=t("ed_end")).pack(side="left")
        self.end_entry = ttk.Entry(times, textvariable=self.end_var, width=13)
        self.end_entry.pack(side="left", padx=(4, 12))
        for entry in (self.start_entry, self.end_entry):
            entry.bind("<Return>", lambda e: self._apply_times(show_errors=True))
            entry.bind("<FocusOut>", lambda e: self._apply_times(show_errors=True))

        ttk.Label(details, text=t("ed_translation")).grid(row=1, column=0, sticky="nw", pady=(6, 0))
        self.text_box = tk.Text(details, height=4, wrap="word", undo=True,
                                font=("Segoe UI", 11))
        self.text_box.grid(row=1, column=1, sticky="nsew", pady=(6, 0), padx=(6, 0))
        self.text_box.tag_configure("found", background="#fff176")
        self.text_box.bind("<KeyRelease>", self._on_text_edit)

        # Duration / characters / reading speed, and the readability warnings, on their own
        # lines under the text: next to the times they were cut off in a small window.
        self.stats_label = ttk.Label(details, foreground="gray")
        self.stats_label.grid(row=2, column=1, sticky="w", padx=(6, 0))
        self.issue_label = ttk.Label(details, foreground="#c0392b")
        self.issue_label.grid(row=3, column=1, sticky="w", padx=(6, 0))
        # Long warnings wrap instead of being cut off.
        self.text_box.bind("<Configure>", lambda e: self.issue_label.configure(
            wraplength=max(100, e.width)), add="+")

        ttk.Label(details, text=t("ed_original")).grid(row=4, column=0, sticky="nw", pady=(4, 0))
        self.orig_box = tk.Text(details, height=3, wrap="word", font=("Segoe UI", 10),
                                background="#f2f2f2", relief="flat", state="disabled")
        self.orig_box.grid(row=4, column=1, sticky="nsew", pady=(4, 0), padx=(6, 0))
        if not self.has_original:
            self._set_readonly_text(self.orig_box, t("ed_no_original"))

        # With an image, a Label's width/height are pixels: keep the preview box fixed.
        pw, ph = self.preview_size
        self._blank = tk.PhotoImage(width=pw, height=ph)
        self.preview = tk.Label(details, text="", image=self._blank, compound="center",
                                width=pw, height=ph, wraplength=pw - 20,
                                background="#202020", foreground="#dddddd")
        self.preview.grid(row=0, column=2, rowspan=5, sticky="ne", padx=(12, 0))

        # --- save / burn
        burn = ttk.LabelFrame(outer, text=t("ed_burn_frame"), padding=8)
        # Reserved before the cue list, so the Save buttons stay visible in a small window.
        burn.pack(side="bottom", fill="x", pady=(8, 0), before=paned)
        row1 = ttk.Frame(burn)
        row1.pack(fill="x")
        self.burn_options = BurnOptions(row1, burn_style)
        self.burn_options.frame.pack(side="left")
        row2 = ttk.Frame(burn)
        row2.pack(fill="x", pady=(8, 0))
        self.save_btn = ttk.Button(row2, text=t("ed_btn_save"), command=self.save)
        self.save_btn.pack(side="left")
        self.burn_btn = ttk.Button(row2, text=t("ed_btn_burn"), command=self.save_and_burn)
        self.burn_btn.pack(side="left", padx=6)
        self.cancel_btn = ttk.Button(row2, text=t("ed_btn_cancel"), command=self.cancel_burn)
        self.cancel_btn.state(["disabled"])
        self.cancel_btn.pack(side="left")
        self.progress = ttk.Progressbar(row2, mode="determinate", maximum=100,
                                        length=int(180 * self.scale))
        self.progress.pack(side="left", padx=8)
        self.open_btn = ttk.Button(row2, text=t("ed_btn_open_folder"),
                                   command=lambda: open_folder_of(self._last_burned or self.srt_path))
        self.open_btn.pack(side="right")
        self.status_var = tk.StringVar(value="")
        ttk.Label(row2, textvariable=self.status_var).pack(side="left", fill="x", expand=True)

    # ------------------------------------------------------------ data helpers

    def _match_originals(self) -> list[str]:
        """Original text per translated cue: by index if counts match, else by time."""
        if not self.orig_cues:
            return [""] * len(self.cues)
        if len(self.orig_cues) == len(self.cues):
            return [o.text for o in self.orig_cues]
        return [self._original_for(c.start, c.end) for c in self.cues]

    def _original_for(self, start: float, end: float) -> str:
        texts = []
        for o in self.orig_cues:
            overlap = min(o.end, end) - max(o.start, start)
            if overlap > 0.15 or (overlap > 0 and overlap >= 0.5 * (o.end - o.start)):
                texts.append(flat_text(o.text))
        return " ".join(texts)

    def _cue_issues(self, i: int) -> list[str]:
        cue = self.cues[i]
        issues = readability_issues(cue.text, cue.start, cue.end)
        if i + 1 < len(self.cues) and self.cues[i + 1].start < cue.end - 0.001:
            issues.append(t("ed_issue_overlap"))
        return issues

    def _row_values(self, i: int) -> list:
        cue = self.cues[i]
        values = [i + 1, format_time(cue.start), format_time(cue.end)]
        if self.has_original:
            values.append(flat_text(self.orig_texts[i]))
        values.append(cue.text.replace("\n", " / "))
        return values

    def _fill_tree(self) -> None:
        self.tree.delete(*self.tree.get_children())
        # Flags are kept per cue, so typing does not re-check 1000+ cues on every key.
        self._flagged = [bool(self._cue_issues(i)) for i in range(len(self.cues))]
        for i in range(len(self.cues)):
            self.tree.insert("", "end", iid=str(i), values=self._row_values(i),
                             tags=("warn",) if self._flagged[i] else ())
        self._update_flag_count()

    def _refresh_row(self, i: int) -> None:
        if 0 <= i < len(self.cues) and self.tree.exists(str(i)):
            self._flagged[i] = bool(self._cue_issues(i))
            self.tree.item(str(i), values=self._row_values(i),
                           tags=("warn",) if self._flagged[i] else ())

    def _update_flag_count(self) -> None:
        n = sum(self._flagged)
        self.flag_label.configure(
            text=t("ed_flag_count", n=n) if n else t("ed_flag_none", total=len(self.cues)))

    def _mark_dirty(self) -> None:
        if not self.dirty:
            self.dirty = True
            self._update_title()

    def _update_title(self) -> None:
        mark = "*" if self.dirty else ""
        self.win.title(t("ed_title", mark=mark, name=os.path.basename(self.srt_path),
                         app=app_name()))

    def _push_undo(self) -> None:
        self._undo.append((copy.deepcopy(self.cues), list(self.orig_texts), self.current))
        del self._undo[:-50]

    def _push_edit_undo(self) -> None:
        """One undo step per cue edited (not per key press), so Undo after typing in
        another cue does not silently throw that typing away."""
        if self._edit_undo_for != self.current:
            self._push_undo()
            self._edit_undo_for = self.current

    def _new_cue(self, start: float, end: float, text: str):
        return subtitles.Cue(start=start, end=end, text=text)

    @staticmethod
    def _set_readonly_text(widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    # ------------------------------------------------------------ selection / details

    def _on_tree_select(self, _event=None) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        index = int(sel[0])
        if index != self.current:
            self._commit_details()
            self._load_details(index)

    def select(self, index: int) -> None:
        if not self.cues:
            self.current = None
            self._clear_details()
            return
        index = max(0, min(index, len(self.cues) - 1))
        self._commit_details()
        self._load_details(index)
        self.tree.selection_set(str(index))
        self.tree.focus(str(index))
        self.tree.see(str(index))

    def select_relative(self, step: int) -> None:
        if self.current is None:
            self.select(0)
        else:
            self.select(self.current + step)

    def _clear_details(self) -> None:
        self.cue_label.configure(text=t("ed_cue"))
        self.start_var.set("")
        self.end_var.set("")
        self.text_box.delete("1.0", "end")
        self.stats_label.configure(text="")
        self.issue_label.configure(text="")
        if self.has_original:
            self._set_readonly_text(self.orig_box, "")

    def _load_details(self, index: int) -> None:
        self.current = index
        self._edit_undo_for = None
        cue = self.cues[index]
        self.cue_label.configure(text=t("ed_cue_n", n=index + 1))
        self.start_var.set(format_time(cue.start))
        self.end_var.set(format_time(cue.end))
        self.text_box.delete("1.0", "end")
        self.text_box.insert("1.0", cue.text)
        self.text_box.edit_reset()
        if self.has_original:
            self._set_readonly_text(self.orig_box, self.orig_texts[index])
        self._update_stats()
        self._schedule_preview((cue.start + cue.end) / 2)

    def _update_stats(self) -> None:
        if self.current is None:
            return
        cue = self.cues[self.current]
        flat = flat_text(cue.text)
        duration = cue.end - cue.start
        cps = len(flat) / duration if duration > 0 else 0
        self.stats_label.configure(text=t("ed_stats", duration=format_number(duration, 2),
                                          chars=len(flat), cps=format_number(cps, 1)))
        issues = self._cue_issues(self.current)
        self.issue_label.configure(text=("⚠ " + t("ed_issue_sep").join(issues)) if issues else "")

    def _on_text_edit(self, _event=None) -> None:
        if self.current is None:
            return
        self.text_box.tag_remove("found", "1.0", "end")
        text = self.text_box.get("1.0", "end-1c")
        cue = self.cues[self.current]
        if text != cue.text:
            self._push_edit_undo()
            cue.text = text
            self._mark_dirty()
            self._refresh_row(self.current)
            self._update_stats()
            self._update_flag_count()

    def _apply_times(self, show_errors: bool = False) -> bool:
        """Copy the start/end entries into the current cue. False if invalid."""
        if self.current is None:
            return True
        cue = self.cues[self.current]
        try:
            start = parse_time(self.start_var.get())
            end = parse_time(self.end_var.get())
            if end <= start:
                raise ValueError(t("ed_time_end_before_start"))
        except ValueError as exc:
            if show_errors:
                self.issue_label.configure(text=t("ed_time_reset", error=exc))
            self.start_var.set(format_time(cue.start))
            self.end_var.set(format_time(cue.end))
            return False
        if abs(start - cue.start) > 0.0005 or abs(end - cue.end) > 0.0005:
            self._push_edit_undo()
            cue.start, cue.end = start, end
            self._mark_dirty()
            for i in (self.current - 1, self.current):
                self._refresh_row(i)
            self._update_stats()
            self._update_flag_count()
            self._schedule_preview((start + end) / 2)
        self.start_var.set(format_time(cue.start))
        self.end_var.set(format_time(cue.end))
        return True

    def _commit_details(self) -> None:
        """Make sure whatever is typed in the detail panel is stored in the cue."""
        if self.current is None or self.current >= len(self.cues):
            return
        self._on_text_edit()
        self._apply_times()

    # ------------------------------------------------------------ cue operations

    def split_cue(self) -> None:
        if self.current is None:
            return
        self._commit_details()
        i = self.current
        cue = self.cues[i]
        words = cue.text.split()
        if len(words) < 2:
            messagebox.showinfo(app_name(), t("ed_split_one_word"), parent=self.win)
            return
        # Split at the word boundary nearest the middle of the text; time is split
        # in the same proportion so each half stays in sync with the speech.
        total = len(" ".join(words))
        k = min(range(1, len(words)),
                key=lambda n: abs(len(" ".join(words[:n])) - total / 2))
        first, second = " ".join(words[:k]), " ".join(words[k:])
        share = len(first) / max(1, len(first) + len(second))
        mid = cue.start + (cue.end - cue.start) * share
        self._push_undo()
        orig = self.orig_texts[i]
        self.cues[i:i + 1] = [self._new_cue(cue.start, mid, first),
                              self._new_cue(mid, cue.end, second)]
        # Each half shows the original cue(s) it overlaps in time.
        self.orig_texts[i:i + 1] = [self._original_for(c.start, c.end) or orig
                                    for c in self.cues[i:i + 2]] if self.orig_cues else [orig, orig]
        self._after_structure_change(i)

    def merge_with_next(self) -> None:
        if self.current is None or self.current + 1 >= len(self.cues):
            self.win.bell()
            if self.current is not None:
                self.status_var.set(t("ed_merge_last"))
            return
        self._commit_details()
        i = self.current
        a, b = self.cues[i], self.cues[i + 1]
        self._push_undo()
        self.cues[i:i + 2] = [self._new_cue(a.start, max(a.end, b.end),
                                            flat_text(a.text + " " + b.text))]
        oa, ob = flat_text(self.orig_texts[i]), flat_text(self.orig_texts[i + 1])
        self.orig_texts[i:i + 2] = [oa if oa == ob else " ".join(s for s in (oa, ob) if s)]
        self._after_structure_change(i)

    def delete_cue(self) -> None:
        if self.current is None:
            return
        self._commit_details()        # so Undo brings the cue back as it was last typed
        i = self.current
        self._push_undo()
        del self.cues[i]
        del self.orig_texts[i]
        self._after_structure_change(min(i, len(self.cues) - 1))

    def undo(self) -> None:
        if not self._undo:
            self.win.bell()
            self.status_var.set(t("ed_nothing_to_undo"))
            return
        self.cues, self.orig_texts, index = self._undo.pop()
        self._after_structure_change(index if index is not None else 0)

    def _after_structure_change(self, index: int) -> None:
        self.current = None              # details belong to the old list; reload them
        self._mark_dirty()
        self._fill_tree()
        if self.cues:
            self.select(index)
        else:
            self._clear_details()

    # ------------------------------------------------------------ find & replace

    def _pattern(self, find: str, match_case: bool):
        return re.compile(re.escape(find), 0 if match_case else re.IGNORECASE)

    def find_next(self, find: str, match_case: bool = False) -> bool:
        """Select the next cue whose translation contains `find` (wraps around)."""
        if not find or not self.cues:
            return False
        self._commit_details()
        pattern = self._pattern(find, match_case)
        start = -1 if self.current is None else self.current
        n = len(self.cues)
        for step in range(1, n + 1):
            i = (start + step) % n
            if pattern.search(self.cues[i].text):
                self.select(i)
                self._highlight(pattern)
                return True
        return False

    def _highlight(self, pattern) -> None:
        self.text_box.tag_remove("found", "1.0", "end")
        text = self.text_box.get("1.0", "end-1c")
        for m in pattern.finditer(text):
            self.text_box.tag_add("found", f"1.0+{m.start()}c", f"1.0+{m.end()}c")

    def replace_current(self, find: str, replacement: str, match_case: bool = False) -> bool:
        """Replace in the selected cue (if it matches), then move to the next match."""
        if not find or self.current is None:
            return False
        self._commit_details()
        pattern = self._pattern(find, match_case)
        cue = self.cues[self.current]
        if pattern.search(cue.text):
            self._push_undo()
            cue.text = pattern.sub(lambda m: replacement, cue.text)
            self._mark_dirty()
            self._refresh_row(self.current)
            self._load_details(self.current)
            self._update_flag_count()
        return self.find_next(find, match_case)

    def replace_all(self, find: str, replacement: str, match_case: bool = False) -> tuple[int, int]:
        """Replace in every translation. Returns (replacements, cues changed)."""
        if not find:
            return 0, 0
        self._commit_details()
        pattern = self._pattern(find, match_case)
        total = changed = 0
        snapshot = (copy.deepcopy(self.cues), list(self.orig_texts), self.current)
        for cue in self.cues:
            new_text, count = pattern.subn(lambda m: replacement, cue.text)
            if count:
                cue.text = new_text
                total += count
                changed += 1
        if changed:
            self._undo.append(snapshot)
            self._mark_dirty()
            self._fill_tree()
            if self.current is not None:
                self._load_details(self.current)
                self.tree.selection_set(str(self.current))
        return total, changed

    def open_find_replace(self) -> None:
        if self._find_dialog and self._find_dialog.winfo_exists():
            self._find_dialog.lift()
            return
        self._find_dialog = FindReplaceDialog(self)

    # ------------------------------------------------------------ frame preview

    def _schedule_preview(self, at: float) -> None:
        """Debounced: only grab a frame once the selection stops moving."""
        if self._preview_after:
            self.win.after_cancel(self._preview_after)
        self._preview_after = self.win.after(150, lambda: self._request_frame(at))

    def _request_frame(self, at: float) -> None:
        self._preview_after = None
        key = round(at, 1)
        self._wanted_frame = key
        if key in self._frame_cache:
            self._show_frame(key)
            return
        if not os.path.isfile(self.video):
            self.preview.configure(image=self._blank, text=t("ed_video_not_found_short"))
            return
        self.preview.configure(image=self._blank, text=t("ed_loading_frame"))
        if key not in self._frame_pending:
            self._frame_pending.add(key)
            threading.Thread(target=self._grab_frame, args=(key,), daemon=True).start()

    def _grab_frame(self, key: float) -> None:
        """Worker thread: ffmpeg -> PNG scaled to PREVIEW_WIDTH."""
        out = os.path.join(self._tmpdir, f"frame_{int(key * 10)}.png")
        pw, ph = self.preview_size
        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", f"{key:.3f}",
               "-i", self.video, "-frames:v", "1", "-vf",
               f"scale=w={pw}:h={ph}:force_original_aspect_ratio=decrease",
               "-y", out]
        error = None
        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=60,
                                  creationflags=_NO_WINDOW)
            if proc.returncode != 0 or not os.path.isfile(out):
                error = ((proc.stderr or b"").decode("utf-8", "replace").strip()[-200:]
                         or t("ed_ffmpeg_failed"))
        except FileNotFoundError:
            error = FFMPEG_MISSING
        except Exception as exc:
            error = str(exc)
        self._queue.put(("frame", (key, None if error else out, error)))

    def _show_frame(self, key: float, error: str | None = None) -> None:
        path = self._frame_cache.get(key)
        if path:
            try:
                self._preview_image = tk.PhotoImage(file=path)
                self.preview.configure(image=self._preview_image, text="")
                return
            except tk.TclError as exc:
                error = str(exc)
        if error == FFMPEG_MISSING:
            error = t("ed_ffmpeg_missing")
        elif error:
            if not self._frame_error_logged:      # once: a broken video fails every frame
                self._frame_error_logged = True
                self.log(t("ed_frame_failed_log", time=format_time(key), error=error))
            error = t("ed_no_picture")
        self.preview.configure(image=self._blank, text=t("ed_no_preview") + "\n" + (error or ""))

    # ------------------------------------------------------------ playback

    def play_cue(self) -> None:
        """Play the selected cue (with the current subtitles) in ffplay."""
        if self.current is None:
            return
        self._commit_details()
        if not os.path.isfile(self.video):
            messagebox.showerror(app_name(), t("ed_video_not_found"), parent=self.win)
            return
        cue = self.cues[self.current]
        stop_process(self._player)
        # Write the current (unsaved) cues to a temp SRT so ffplay shows them; a bare
        # file name with cwd=tmpdir avoids escaping Windows paths in the filter.
        args = []
        try:
            subtitles.write_srt(self.cues, os.path.join(self._tmpdir, "preview.srt"))
            args = ["-vf", "subtitles=preview.srt"]
        except Exception:
            pass
        title = t("ed_player_title", n=self.current + 1, text=flat_text(cue.text)[:60])
        cmd = (["ffplay", "-hide_banner", "-loglevel", "error", "-ss", f"{cue.start:.3f}",
                "-t", f"{max(0.3, cue.end - cue.start):.3f}", "-autoexit", "-x", "960",
                "-window_title", title] + args + [self.video])
        try:
            self._player = subprocess.Popen(cmd, cwd=self._tmpdir, creationflags=_NO_WINDOW,
                                            stdin=subprocess.DEVNULL,
                                            stdout=subprocess.DEVNULL,
                                            stderr=subprocess.DEVNULL)
        except FileNotFoundError:
            messagebox.showerror(app_name(), t("ed_ffplay_missing"), parent=self.win)

    # ------------------------------------------------------------ save / burn

    def _sort_cues(self) -> None:
        order = sorted(range(len(self.cues)), key=lambda i: (self.cues[i].start, i))
        if order != list(range(len(self.cues))):
            cur = self.current
            self.cues = [self.cues[i] for i in order]
            self.orig_texts = [self.orig_texts[i] for i in order]
            self.current = None
            self._fill_tree()
            if cur is not None:
                self.select(order.index(cur))

    def save(self) -> bool:
        self._commit_details()
        self._sort_cues()
        try:
            backup = self.srt_path + ".bak"
            if not self._backed_up and os.path.isfile(self.srt_path) and not os.path.exists(backup):
                shutil.copy2(self.srt_path, backup)   # first original kept once
            self._backed_up = True
            subtitles.write_srt(self.cues, self.srt_path)
        except Exception as exc:
            if isinstance(exc, PermissionError):
                reason = t("ed_no_permission")
            else:
                reason = exc.strerror if isinstance(exc, OSError) and exc.strerror else str(exc)
            messagebox.showerror(app_name(), t("ed_save_failed", path=self.srt_path, reason=reason),
                                 parent=self.win)
            return False
        self.dirty = False
        self._update_title()
        self.status_var.set(t("ed_saved", name=os.path.basename(self.srt_path)))
        return True

    @property
    def burning(self) -> bool:
        return bool(self._burn_thread and self._burn_thread.is_alive())

    def save_and_burn(self) -> None:
        if self.burning:
            return
        if not os.path.isfile(self.video):
            messagebox.showerror(app_name(), t("ed_video_not_found_path", path=self.video),
                                 parent=self.win)
            return
        if not self.save():
            return
        try:
            eng = get_engine()
            style = eng.BurnStyle(**self.burn_options.values())
        except Exception as exc:
            messagebox.showerror(app_name(), t("ed_engine_failed", error=exc), parent=self.win)
            return
        self._burn_cancel = threading.Event()
        self._set_burning(True)
        self.progress["value"] = 0
        self.status_var.set(t("ed_burning"))
        self._burn_thread = threading.Thread(target=self._burn_worker,
                                             args=(eng, style, self._burn_cancel), daemon=True)
        self._burn_thread.start()

    def _burn_worker(self, eng, style, cancel: threading.Event) -> None:
        """Worker thread: talks to the UI only through self._queue."""
        q = self._queue
        try:
            path = eng.burn_video(self.video, self.srt_path, style=style,
                                  log=lambda m: q.put(("burn_log", str(m))),
                                  progress=lambda p: q.put(("burn_progress", p)),
                                  cancel=cancel)
            q.put(("burn_done", path))
        except Exception as exc:
            if isinstance(exc, getattr(eng, "Cancelled", ())) or cancel.is_set():
                q.put(("burn_cancelled", None))
            else:
                q.put(("burn_failed", (exc, traceback.format_exc())))

    def cancel_burn(self) -> None:
        if self._burn_cancel and not self._burn_cancel.is_set():
            self._burn_cancel.set()
            self.status_var.set(t("ed_cancelling"))
            self.cancel_btn.state(["disabled"])

    def _set_burning(self, busy: bool) -> None:
        self.burn_btn.state(["disabled"] if busy else ["!disabled"])
        self.save_btn.state(["disabled"] if busy else ["!disabled"])
        self.cancel_btn.state(["!disabled"] if busy else ["disabled"])
        self.burn_options.set_enabled(not busy)

    # ------------------------------------------------------------ queue pump

    def _poll_queue(self) -> None:
        if self.closed:
            return
        try:
            while True:
                kind, payload = self._queue.get_nowait()
                if kind == "frame":
                    key, path, error = payload
                    self._frame_pending.discard(key)
                    self._frame_cache[key] = path
                    if key == self._wanted_frame:
                        self._show_frame(key, error)
                elif kind == "burn_progress":
                    try:
                        self.progress["value"] = max(0.0, min(1.0, float(payload))) * 100
                    except (TypeError, ValueError):
                        pass
                elif kind == "burn_log":
                    line = payload.strip().splitlines()[-1] if payload.strip() else ""
                    if line:
                        self.status_var.set(engine_message(line.strip())[:120])
                elif kind == "burn_done":
                    self._on_burn_done(payload)
                elif kind == "burn_cancelled":
                    self._set_burning(False)
                    self.progress["value"] = 0
                    self.status_var.set(t("ed_burn_cancelled"))
                elif kind == "burn_failed":
                    exc, tb = payload
                    self._set_burning(False)
                    self.progress["value"] = 0
                    self.status_var.set(t("ed_burn_failed_status"))
                    self.log(tb)
                    first = str(exc).strip().splitlines()[0] if str(exc).strip() else ""
                    messagebox.showerror(
                        app_name(), t("ed_burn_failed") + "\n\n"
                        + (engine_message(first.strip()) + "\n\n" if first else "")
                        + t("ed_burn_failed_saved")
                        + (" " + t("ed_burn_failed_log") if self._has_log else ""),
                        parent=self.win)
        except queue.Empty:
            pass
        if self.closing and not self.burning and self._queue.empty():
            self.destroy()                # the cancelled burn has stopped: finish closing
            return
        self.win.after(100, self._poll_queue)

    def _on_burn_done(self, path: str) -> None:
        self._set_burning(False)
        self.progress["value"] = 100
        self._last_burned = path
        self.status_var.set(t("ed_video_saved_status", path=path))
        if self.on_burned:
            try:
                self.on_burned(path)
            except Exception:
                self.log(traceback.format_exc())
        if not self.closing and messagebox.askyesno(
                app_name(), t("ed_video_saved", path=path), parent=self.win):
            open_folder_of(path)

    # ------------------------------------------------------------ closing

    def close(self) -> bool:
        """Ask about unsaved edits / a running burn, then close.

        Returns False if the user chose to keep the window open. While a cancelled burn
        is stopping, the window is hidden and closes itself shortly after (self.closed
        becomes True then).
        """
        if self.closing:
            return True
        if self.burning and not messagebox.askyesno(
                app_name(), t("ed_close_while_burning"), parent=self.win):
            return False
        self._commit_details()
        if self.dirty:
            answer = messagebox.askyesnocancel(app_name(), t("ed_save_changes"), parent=self.win)
            if answer is None or (answer and not self.save()):
                return False
        if self.burning:
            self.cancel_burn()
            self.closing = True          # _poll_queue destroys the window once ffmpeg stopped
            self.win.withdraw()
        else:
            self.destroy()
        return True

    def destroy(self) -> None:
        """Close without prompting."""
        self.closed = True
        stop_process(self._player)
        if self._find_dialog and self._find_dialog.winfo_exists():
            self._find_dialog.destroy()
        try:
            self.win.destroy()
        except tk.TclError:
            pass
        shutil.rmtree(self._tmpdir, ignore_errors=True)
        if self.on_closed:
            self.on_closed()


class FindReplaceDialog(tk.Toplevel):
    """Find & replace in the translations of a SubtitleEditor."""

    def __init__(self, editor: SubtitleEditor):
        super().__init__(editor.win)
        self.editor = editor
        self.title(t("ed_find_title"))
        self.transient(editor.win)
        self.resizable(False, False)
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        self.find_var = tk.StringVar()
        self.repl_var = tk.StringVar()
        self.case_var = tk.BooleanVar(value=False)
        ttk.Label(body, text=t("ed_find_label")).grid(row=0, column=0, sticky="w")
        find_entry = ttk.Entry(body, textvariable=self.find_var, width=34)
        find_entry.grid(row=0, column=1, padx=6, pady=3)
        ttk.Label(body, text=t("ed_replace_label")).grid(row=1, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.repl_var, width=34).grid(row=1, column=1, padx=6, pady=3)
        ttk.Checkbutton(body, text=t("ed_match_case"), variable=self.case_var).grid(
            row=2, column=1, sticky="w", padx=6)
        buttons = ttk.Frame(body)
        buttons.grid(row=0, column=2, rowspan=4, sticky="n")
        actions = ((t("ed_find_next"), self.find_next), (t("ed_replace"), self.replace),
                   (t("ed_replace_all"), self.replace_all), (t("ed_close"), self.destroy))
        width = max(12, max(len(text) for text, _ in actions) + 2)   # same width, none clipped
        for text, cmd in actions:
            ttk.Button(buttons, text=text, command=cmd, width=width).pack(pady=2)
        self.status = ttk.Label(body, foreground="gray")
        self.status.grid(row=3, column=0, columnspan=2, sticky="w", pady=(6, 0))
        find_entry.focus_set()
        self.bind("<Return>", lambda e: self.find_next())
        self.bind("<Escape>", lambda e: self.destroy())

    def find_next(self) -> None:
        found = self.editor.find_next(self.find_var.get(), self.case_var.get())
        self.status.configure(text="" if found else t("ed_not_found"))

    def replace(self) -> None:
        found = self.editor.replace_current(self.find_var.get(), self.repl_var.get(),
                                            self.case_var.get())
        self.status.configure(text="" if found else t("ed_no_more_matches"))

    def replace_all(self) -> None:
        total, cues = self.editor.replace_all(self.find_var.get(), self.repl_var.get(),
                                              self.case_var.get())
        self.status.configure(text=t("ed_replaced", total=total, cues=cues))


def open_editor(parent, video_path, translated_srt, original_srt=None, burn_style=None,
                on_burned=None, log=None) -> SubtitleEditor:
    """Open the review/edit window and return the SubtitleEditor.

    log(text) receives error details (the main window's log); default: stderr.
    """
    return SubtitleEditor(parent, video_path, translated_srt, original_srt=original_srt,
                          burn_style=burn_style, on_burned=on_burned, log=log)


def ensure_std_streams() -> None:
    """Started with pythonw (no console), sys.stdout/stderr are None and any print or
    progress bar of a library would crash: send that output nowhere instead."""
    for name in ("stdout", "stderr"):
        if getattr(sys, name) is None:
            setattr(sys, name, open(os.devnull, "w", encoding="utf-8"))


def main(argv: list[str]) -> int:
    ensure_std_streams()
    i18n.set_language(load_ui_language())   # the main window's choice, Turkish by default
    enable_dpi_awareness()
    root = tk.Tk()
    root.withdraw()
    set_window_icon(root)
    style = ttk.Style(root)
    if "vista" in style.theme_names():
        style.theme_use("vista")
    args = argv[1:]
    if len(args) < 2:
        # No/partial arguments: ask for the files.
        print("Usage: python editor.py VIDEO TRANSLATED_SRT [ORIGINAL_SRT]")
        video = args[0] if args else filedialog.askopenfilename(
            title=t("ed_choose_video"),
            filetypes=[(t("ed_video_files"), "*.mp4 *.mkv *.mov *.avi *.webm *.m4v"),
                       (t("ed_all_files"), "*.*")])
        if not video:
            return 1
        srt = filedialog.askopenfilename(title=t("ed_choose_srt"),
                                         initialdir=os.path.dirname(video),
                                         filetypes=[(t("ed_srt_files"), "*.srt")])
        if not srt:
            return 1
        args = [video, srt]
    try:
        ed = open_editor(root, args[0], args[1], args[2] if len(args) > 2 else None)
    except Exception as exc:
        messagebox.showerror(app_name(), t("ed_open_failed", error=exc))
        return 1
    ed.on_closed = root.destroy
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
