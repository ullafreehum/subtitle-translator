"""User-interface language (Turkish by default, English available).

The windows ask for their texts with t("key"), e.g. t("start") -> "Başlat".
Texts live in separate tables so each window keeps its own:

    i18n_app.py     main window (app.py)
    i18n_editor.py  subtitle editor (editor.py)
    i18n_engine.py  progress/error messages coming from engine.py and translation.py

Each table is a dict {key: {"tr": "...", "en": "..."}}. Texts may contain
{placeholders}: t("files_added", n=3).

The engine and the command line stay in English; engine messages are shown
in the window's language through engine_message().
"""

from __future__ import annotations

import importlib
import re

LANGUAGES = {"tr": "Türkçe", "en": "English"}
DEFAULT = "tr"

_lang = DEFAULT
_strings: dict[str, dict[str, str]] = {}
_patterns: list[tuple[re.Pattern, dict[str, str]]] = []
_loaded = False


def _load() -> None:
    """Merge the text tables (missing tables are skipped, so the app still starts)."""
    global _loaded
    if _loaded:
        return
    _loaded = True
    for name in ("i18n_app", "i18n_editor", "i18n_engine"):
        try:
            mod = importlib.import_module(name)
        except ImportError:
            continue
        _strings.update(getattr(mod, "STRINGS", {}))
        for pattern, texts in getattr(mod, "PATTERNS", []):
            _patterns.append((re.compile(pattern), texts))


def set_language(code: str | None) -> str:
    """Switch the language; unknown codes fall back to Turkish. Returns the code used."""
    global _lang
    _lang = code if code in LANGUAGES else DEFAULT
    return _lang


def language() -> str:
    return _lang


def t(key: str, **kwargs) -> str:
    """Text for `key` in the current language (English, then the key itself, as fallback)."""
    _load()
    entry = _strings.get(key)
    text = (entry.get(_lang) or entry.get("en")) if entry else key
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def engine_message(message: str) -> str:
    """Show an English engine message in the current language.

    PATTERNS in i18n_engine.py are (regex, {"tr": template}) pairs; the template
    can use the regex's named groups, e.g. r"Saved (?P<name>.+)" -> "Kaydedildi: {name}".
    Unknown messages are returned unchanged.
    """
    _load()
    if _lang == "en":
        return message
    lines = message.split("\n")
    out = []
    for line in lines:
        for regex, texts in _patterns:
            m = regex.fullmatch(line.strip())
            if m and _lang in texts:
                indent = line[: len(line) - len(line.lstrip())]
                line = indent + texts[_lang].format(**m.groupdict())
                break
        out.append(line)
    return "\n".join(out)


def missing_keys() -> dict[str, list[str]]:
    """Keys whose text is missing in a language (used by the tests)."""
    _load()
    return {code: sorted(k for k, v in _strings.items() if not v.get(code)) for code in LANGUAGES}
