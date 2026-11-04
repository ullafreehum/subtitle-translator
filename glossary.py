"""User glossary: names kept exactly as written, and forced term translations.

File format (UTF-8, see glossary.example.txt):
    # comment
    DİLGEM                  <- outside any section: keep exactly as written
    [en>tr]                 <- forced translations for English -> Turkish
    trainees = kursiyerler

Matching is case-insensitive and whole-word; Turkish dotted/dotless i
(İ, I, ı, i) are treated as the same letter, so "Dilgem", "DILGEM" and
"dilgem" all match "DİLGEM". No heavy imports here.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path

_HERE = Path(__file__).resolve().parent
GLOSSARY_PATH = str(_HERE / "glossary.txt")
EXAMPLE_PATH = str(_HERE / "glossary.example.txt")

_SECTION = re.compile(r"^\[\s*([A-Za-z-]+)\s*>\s*([A-Za-z-]+)\s*\]$")
_I_VARIANTS = "iIİı"
_I_FOLD = str.maketrans({c: "i" for c in _I_VARIANTS})
WHISPER_PROMPT_MAX = 400


# --------------------------------------------------------------------------
# Term matching helpers (also used by translation.py)
# --------------------------------------------------------------------------

def fold(term: str) -> str:
    """Comparison key: lower case, Turkish i variants unified, single spaces."""
    return " ".join(term.translate(_I_FOLD).lower().split())


def term_pattern(term: str) -> str:
    """Regex for a term (use with re.IGNORECASE): flexible spaces, any Turkish i."""
    parts: list[str] = []
    for ch in term.strip():
        if ch.isspace():
            if parts[-1] != r"\s+":
                parts.append(r"\s+")
        elif ch in _I_VARIANTS:
            parts.append(f"[{_I_VARIANTS}]")
        else:
            parts.append(re.escape(ch))
    return "".join(parts)


def is_abbreviation(term: str) -> bool:
    """Short all-capitals terms (up to 4 letters, e.g. ABA, CARS, DEHB) are case-sensitive."""
    letters = [c for c in term if c.isalpha()]
    return 0 < len(letters) <= 4 and all(c.isupper() for c in letters)


def _case_pattern(term: str) -> str:
    """Regex for a term with its case rule.

    - Short abbreviations (ABA, CARS) only match in capitals, so "cars" and
      Turkish "aba"/"dir" are left alone.
    - Longer all-capitals names (DİLGEM, JASPER, CALMS) match in capitals or with
      just a capital first letter ("Dilgem", "Jasper"), but not in lower case,
      so everyday words like "calms" or "prompt" are left alone.
    - Everything else matches in any case.
    """
    letters = [c for c in term if c.isalpha()]
    if not letters or not all(c.isupper() for c in letters):
        return f"(?i:{term_pattern(term)})"
    if is_abbreviation(term):
        return term_pattern(term)
    title = term[0] + term[1:].replace("İ", "i").replace("I", "ı").lower()
    return f"(?:{term_pattern(term)}|{term_pattern(title)})"


def contains_term(text: str, term: str) -> bool:
    """True if `term` starts a word in `text` (suffixes allowed: "kursiyerlerle")."""
    return re.search(r"(?<!\w)" + term_pattern(term), text, re.IGNORECASE) is not None


class TermMap:
    """Replace whole-word, case-insensitive occurrences of terms.

    mapping: term -> replacement. Longer terms win ("DIR Floortime" before
    "Floortime"), and replaced text is never matched again. Attached suffixes
    after an apostrophe stay: "Jasper'ı" -> "JASPER'ı".
    """

    def __init__(self, mapping: dict[str, str], suffixes: bool = False, joiner: str = "'"):
        """suffixes=True also matches a term with letters glued on (Turkish
        "filial terapide"); the replacement keeps them, after `joiner`."""
        self._joiner = joiner
        self._map = {fold(k): v for k, v in mapping.items() if k.strip()}
        terms = sorted((k for k in mapping if k.strip()), key=len, reverse=True)
        alts = [_case_pattern(t) for t in terms]
        end = r"(\w*)" if suffixes else r"()(?!\w)"
        self._regex = (re.compile(r"(?<!\w)(" + "|".join(alts) + ")" + end) if terms else None)

    def __bool__(self) -> bool:
        return self._regex is not None

    def find(self, text: str) -> list[str]:
        """Replacements for the terms found in text, in order of appearance."""
        if self._regex is None:
            return []
        return [self._value(m) for m in self._regex.finditer(text)]

    def sub(self, text: str, repl=None) -> str:
        """Replace each match with its mapped value, or with repl(value, matched_text)."""
        if self._regex is None:
            return text

        def one(m: re.Match) -> str:
            value = self._value(m) if repl is None else repl(self._value(m), m.group(1))
            return value + (self._joiner + m.group(2) if m.group(2) else "")

        return self._regex.sub(one, text)

    def _value(self, m: re.Match) -> str:
        return self._map.get(fold(m.group(1)), m.group(1))


# --------------------------------------------------------------------------
# Glossary
# --------------------------------------------------------------------------

def _base(code: str | None) -> str:
    return (code or "").lower().split("-")[0]


@dataclass
class Glossary:
    keep_terms: list[str] = field(default_factory=list)
    # (source, target) -> {source term: forced translation}
    pairs: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)
    # [hints]: words that only help speech recognition (never forced).
    hints: list[str] = field(default_factory=list)

    def translations(self, source: str, target: str) -> dict[str, str]:
        """Forced term translations for a language pair (Whisper codes, e.g. "en", "tr")."""
        return dict(self.pairs.get((_base(source), _base(target)), {}))

    def whisper_prompt(self) -> str:
        """Short comma-separated list of hints and keep_terms, for Whisper's initial_prompt.

        Hints come first: they are chosen for recognition. Whisper only uses
        about 220 tokens of prompt, so the list is cut at WHISPER_PROMPT_MAX.
        """
        out = ""
        for term in dict.fromkeys(self.hints + self.keep_terms):
            candidate = f"{out}, {term}" if out else term
            if len(candidate) > WHISPER_PROMPT_MAX - 1:
                break
            out = candidate
        return out + "." if out else ""

    def fix_terms(self, text: str, lang: str | None = None) -> str:
        """Restore the exact spelling of keep_terms ("Dilgem'in" -> "DİLGEM'in").

        With `lang`, also apply that language's correction section, e.g.
        [tr>tr] "terapotik = terapötik" fixes a word speech recognition mishears.
        """
        if lang and self.translations(lang, lang):
            # Corrections also match with a suffix ("Filaterapide" -> "filial terapide").
            text = TermMap(self.translations(lang, lang), suffixes=True, joiner="").sub(text)
        return TermMap({t: t for t in self.keep_terms}).sub(text)


def parse_glossary(content: str) -> Glossary:
    g = Glossary()
    section: dict[str, str] | None = None
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _SECTION.match(line)
        if m:
            section = g.pairs.setdefault((_base(m.group(1)), _base(m.group(2))), {})
        elif line.lower() == "[hints]":
            section = g.hints  # type: ignore[assignment]
        elif section is g.hints:
            if line not in g.hints:
                g.hints.append(line)
        elif section is None:
            if line not in g.keep_terms:
                g.keep_terms.append(line)
        elif "=" in line:
            src, tgt = (s.strip() for s in line.split("=", 1))
            if src and tgt:
                section[src] = tgt
    return g


def load_glossary(path: str | None = None) -> Glossary:
    """Load the glossary file. Never raises: a missing/unreadable file gives an empty Glossary.

    With the default path, glossary.txt is created from glossary.example.txt
    the first time.
    """
    target = Path(path or GLOSSARY_PATH)
    try:
        if path is None and not target.exists() and Path(EXAMPLE_PATH).is_file():
            shutil.copyfile(EXAMPLE_PATH, target)
        return parse_glossary(target.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError):
        return Glossary()
