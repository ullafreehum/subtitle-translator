"""Subtitle cues: readable, well-timed cues from Whisper word timestamps, line wrapping,
and SRT / WebVTT reading and writing.

Pure standard library (no heavy imports) so the GUI, editor and tests can import it cheaply.

The rules follow common professional subtitling guidelines (Netflix / BBC style):

* at most ``max_lines`` lines of ``max_chars_per_line`` characters per cue;
* on screen between ``min_duration`` and ``max_duration`` seconds;
* reading speed at most ``max_cps`` characters per second -- the end time is extended into
  the following silence when needed;
* at least ``min_gap`` seconds between cues; gaps shorter than 0.5 s are closed down to
  ``min_gap`` so subtitles don't flicker;
* cues are split at natural points: sentence ends, then pauses, then commas / clauses,
  then before conjunctions; never inside a number or after a title ("Dr. Smith"), and
  1-word "orphan" cues are avoided.

Widths are *display* widths: East Asian wide characters (Chinese, Japanese) count as 2,
combining marks (Thai vowels and tone marks) as 0. With the default 42 / 17 cps this gives
21 CJK characters per line and ~8.5 CJK characters per second, close to the usual norms.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache


@dataclass
class Cue:
    start: float   # seconds
    end: float     # seconds
    text: str      # may contain "\n" line breaks


# --------------------------------------------------------------------------
# Characters and widths
# --------------------------------------------------------------------------

# Scripts written without spaces between words (lines may break between any two characters):
# Thai, Lao, Myanmar, Khmer, CJK punctuation / kana / ideographs, full-width forms.
_NO_SPACE_RE = re.compile(
    "[\u0e00-\u0eff\u1000-\u109f\u1780-\u17ff\u2e80-\u2fff\u3000-\u30ff\u31f0-\u31ff"
    "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef\U00020000-\U0003ffff]"
)
_SENTENCE_END = set(".?!…。！？‼⁇⁈⁉")
_CLAUSE_END = set(",;:–—，、；：")
_CLOSERS = "\"'”’»)]}」』）》〉】"          # may follow the final punctuation of a word
_PUNCT = "\"'“”‘’«»()[]{}¿¡.,;:!?…–—-「」『』（）《》〈〉【】。，、；：！？"


@lru_cache(maxsize=4096)
def _char_width(ch: str) -> int:
    if unicodedata.combining(ch) or unicodedata.category(ch) in ("Mn", "Me", "Cf"):
        return 0
    return 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1


@lru_cache(maxsize=65536)
def _width(text: str) -> int:
    """Display width of `text` (CJK = 2 per character, combining marks = 0)."""
    return sum(_char_width(c) for c in text)


@lru_cache(maxsize=8192)
def _no_space(ch: str) -> bool:
    return bool(_NO_SPACE_RE.match(ch))


@lru_cache(maxsize=65536)
def _glued(prev: str, ch: str) -> bool:
    """True when no line break is allowed between `prev` and `ch` (no whitespace between)."""
    cat = unicodedata.category(ch)
    if _char_width(ch) == 0 or cat in ("Pe", "Pf", "Po"):   # combining mark / closing punctuation
        return True
    if unicodedata.category(prev) in ("Ps", "Pi"):           # after an opening bracket / quote
        return True
    return not _no_space(ch) and not _no_space(prev)         # inside a normal word


@lru_cache(maxsize=16384)
def _units(text: str) -> tuple[tuple[str, str], ...]:
    """Split text into unbreakable units as (separator_before, unit) pairs.

    Words for spaced languages; single characters (with attached punctuation and
    combining marks) for Chinese, Japanese, Thai...
    """
    units: list[list[str]] = []
    sep = ""
    for ch in text:
        if ch.isspace():
            sep = " " if units else ""
            continue
        if units and not sep and _glued(units[-1][1][-1], ch):
            units[-1][1] += ch
        else:
            units.append([sep, ch])
        sep = ""
    return tuple((s, u) for s, u in units)


def _clean(text: str) -> str:
    """Collapse whitespace. A line break between two no-space characters is just removed."""
    text = re.sub(r"(?<=\S)[ \t]*\n[ \t]*(?=\S)",
                  lambda m: "" if _no_space(m.string[m.start() - 1]) and _no_space(m.string[m.end()])
                  else " ", text.strip())
    return " ".join(text.split())


# --------------------------------------------------------------------------
# Where to break (shared by cue splitting and line wrapping)
# --------------------------------------------------------------------------

SENTENCE, CLAUSE, CONJ, PHRASE, ARTICLE, PLAIN, WEAK, NOSPLIT = range(8)

# Words a new line / cue may comfortably start with.
_CONJUNCTIONS = {
    # English
    "and", "but", "or", "nor", "so", "yet", "because", "that", "which", "who", "whom", "whose",
    "when", "while", "where", "if", "then", "although", "though", "since", "until", "unless",
    "after", "before", "as", "whether", "than",
    # Turkish
    "ve", "ama", "fakat", "ancak", "çünkü", "veya", "ya", "yahut", "ki", "eğer", "ise",
    # German / French / Spanish / Italian / Portuguese
    "und", "aber", "oder", "weil", "dass", "wenn", "et", "mais", "ou", "parce", "que", "qui",
    "quand", "y", "pero", "o", "porque", "cuando", "e", "ma", "perché", "quando", "mas",
}
# Prepositions: a new phrase starts before them (a fair place to break).
_PHRASE_STARTS = {
    "to", "in", "on", "at", "for", "with", "from", "by", "into", "about", "during", "without",
    "through", "between", "like",                             # not "of": "a lot of", "most of"
    "en", "con", "per", "por", "para", "mit", "für", "von", "zu", "avec", "dans", "pour",
}
# Articles: fine to start a new line, but a cue break there often splits verb and object.
_ARTICLES = {"a", "an", "the", "der", "die", "das", "ein", "eine", "le", "la", "les", "un", "une",
             "des", "el", "los", "las", "il", "lo", "gli", "bir"}
# Words a line / cue should not end with (articles, prepositions, subject pronouns...).
_WEAK_ENDINGS = {
    "a", "an", "the", "of", "to", "in", "on", "at", "for", "with", "from", "by", "into", "about",
    "my", "your", "his", "her", "our", "their", "its", "this", "these", "those", "and", "or",
    "but", "i", "we", "they", "he", "she", "very", "is", "are", "was", "were", "be", "not",
    "it's", "i'm", "we're", "they're", "you're", "that's", "there's", "he's", "she's", "i've",
    "we've", "i'd", "we'd", "i'll", "we'll", "don't", "can't", "will", "would", "can", "could",
    "bir", "bu", "şu", "ve", "çok",
    "der", "die", "das", "ein", "eine", "le", "la", "les", "un", "une", "des", "de", "el", "los",
    "las", "il", "lo", "gli",
}
# Titles and abbreviations that are never followed by a break ("Dr. Smith").
_ABBREVIATIONS = {"dr.", "mr.", "mrs.", "ms.", "prof.", "st.", "mt.", "jr.", "sr.", "vs.",
                  "e.g.", "i.e.", "fig.", "dr", "mr", "mrs", "ms", "prof", "doç.", "av.", "sn."}
# Words that belong to a preceding number ("10 %", "5 pm").
_NUMBER_FOLLOWERS = {"%", "percent", "per", "am", "pm", "a.m.", "p.m.", "km", "kg", "cm", "mm",
                     "m", "g", "ml", "l", "tl", "$", "€", "£", "°", "°c"}
_INITIAL_RE = re.compile(r"[A-Z]\.")


def _is_name(word: str) -> bool:
    core = word.strip(_PUNCT)
    return len(core) > 1 and core[0].isupper() and core.isalpha() and word[-1] not in _PUNCT


@lru_cache(maxsize=65536)
def _break_class(before: str, after: str) -> int:
    """Classify a break between the word `before` and the word `after`."""
    a, b = before.strip(), after.strip()
    if not a or not b:
        return PLAIN
    a_core = a.rstrip(_CLOSERS) or a
    a_low = a_core.lower()
    b_low = b.lower().strip(_PUNCT) or b.lower()
    if a_core[-1].isdigit() and (b[0].isdigit() or b_low in _NUMBER_FOLLOWERS):
        return NOSPLIT                                   # "1 000", "10 %"
    if a_low in _ABBREVIATIONS or _INITIAL_RE.fullmatch(a_core):
        return NOSPLIT                                   # "Dr. Smith", "J. Smith"
    if a_core[-1] in _SENTENCE_END:
        return SENTENCE
    if a_core[-1] in _CLAUSE_END:
        return CLAUSE
    if a_low.strip(_PUNCT).replace("’", "'") in _WEAK_ENDINGS:
        return WEAK
    if b_low in _CONJUNCTIONS:
        return CONJ
    if b_low in _PHRASE_STARTS:
        return PHRASE
    if b_low in _ARTICLES:
        return ARTICLE
    if _is_name(a_core) and _is_name(b) and a_core != "I":
        return WEAK                                      # inside a name: "Ayşe Yılmaz"
    return PLAIN


# Costs of ending a cue / a line at a break of each class (lower = better).
_CUE_BREAK_COST = {SENTENCE: 0, CLAUSE: 12, CONJ: 20, PHRASE: 32, ARTICLE: 45, PLAIN: 60, WEAK: 80,
                   NOSPLIT: 300}
_LINE_BREAK_COST = {SENTENCE: -20, CLAUSE: -14, CONJ: -10, PHRASE: -6, ARTICLE: -4, PLAIN: 0, WEAK: 8,
                    NOSPLIT: 40}


# --------------------------------------------------------------------------
# Line wrapping
# --------------------------------------------------------------------------

def _min_lines(units: list[tuple[str, str]], width: int) -> int:
    """Number of lines a greedy fill needs (the minimum possible)."""
    lines, cur = 1, 0
    for k, (sep, unit) in enumerate(units):
        w = _width(unit)
        if k and cur + len(sep) + w > width:
            lines, cur = lines + 1, w
        else:
            cur += (len(sep) if k else 0) + w
    return lines


def wrap_text(text: str, width: int = 42, max_lines: int = 2) -> str:
    """Wrap text into at most `max_lines` balanced lines of at most `width` columns.

    Uses as few lines as possible; with several lines, break where it reads best
    (after punctuation, before a conjunction, not after an article, never inside
    "Dr. Smith" or a number) while keeping lines balanced, the bottom line a little
    longer (pyramid shape). Text too long for `max_lines` lines still gets exactly
    `max_lines` balanced lines (some longer than `width`). Languages without spaces
    (zh, ja, th) are broken between characters.
    """
    return _layout(_units(_clean(text)), width, max_lines)[0]


def _join_units(units) -> str:
    return "".join((sep if k else "") + unit for k, (sep, unit) in enumerate(units))


@lru_cache(maxsize=16384)
def _layout(units: tuple[tuple[str, str], ...], width: int, max_lines: int) -> tuple[str, float]:
    """Wrap units into lines; returns the wrapped text and its layout cost (lower = better)."""
    n = min(_min_lines(units, width), max(max_lines, 1), len(units))
    if n <= 1:
        return _join_units(units), 0.0

    # prefix[k] = width of units[0:k] including separators; line(i, j) = units[i:j]
    prefix = [0]
    for sep, unit in units:
        prefix.append(prefix[-1] + len(sep) + _width(unit))
    def line_width(i: int, j: int) -> int:
        return prefix[j] - prefix[i] - len(units[i][0])

    total = line_width(0, len(units))
    target = total / n
    break_cost = [0] + [_LINE_BREAK_COST[_break_class(units[k - 1][1], units[k][1])]
                        for k in range(1, len(units))]

    def line_cost(i: int, j: int, last: bool) -> tuple[int, float]:
        w = line_width(i, j)
        over = max(0, w - width) ** 2                    # only > 0 when it can't fit
        dev = w - target
        shape = abs(dev) * (1.5 if dev > 0 and not last else 1.0)   # prefer pyramid
        return over, shape + (0 if last else break_cost[j])

    m = len(units)
    if n == 2:                                           # the usual case: try every break
        def two(k: int) -> tuple[int, float]:
            (o1, c1), (o2, c2) = line_cost(0, k, False), line_cost(k, m, True)
            return o1 + o2, c1 + c2
        k = min(range(1, m), key=two)
        return _join_units(units[:k]) + "\n" + _join_units(units[k:]), two(k)[1]

    # best[l][j]: best (overflow, cost, previous break) for units[0:j] in l lines
    INF = (math.inf, math.inf, -1)
    best = [[INF] * (m + 1) for _ in range(n + 1)]
    best[0][0] = (0, 0.0, -1)
    for lines in range(1, n + 1):
        for j in range(lines, m + 1):
            if lines == n and j != m:
                continue
            for i in range(lines - 1, j):
                prev = best[lines - 1][i]
                if prev[0] == math.inf:
                    continue
                over, cost = line_cost(i, j, j == m)
                cand = (prev[0] + over, prev[1] + cost, i)
                if cand[:2] < best[lines][j][:2]:
                    best[lines][j] = cand
    # Walk back the chosen breaks.
    breaks, j = [], m
    for lines in range(n, 0, -1):
        i = best[lines][j][2]
        breaks.append((i, j))
        j = i
    text = "\n".join(_join_units(units[i:j]) for i, j in reversed(breaks))
    return text, best[n][m][1]


# --------------------------------------------------------------------------
# Building cues from Whisper segments
# --------------------------------------------------------------------------

@dataclass
class _Token:
    start: float
    end: float
    text: str
    space: bool       # separated from the previous token by a space
    seg_start: bool   # first token of a Whisper segment


def _get(obj, key: str, default=None):
    """Read a field from a dict or from a faster-whisper Segment/Word object."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _tokens(segments) -> list[_Token]:
    """Flatten segments into timed word tokens.

    Segments without word timestamps are split into words (or characters for CJK/Thai)
    with times spread proportionally to their width over the segment.
    """
    tokens: list[_Token] = []
    for seg in segments or []:
        s_start = float(_get(seg, "start", 0.0) or 0.0)
        s_end = max(float(_get(seg, "end", s_start) or s_start), s_start)
        words = [w for w in (_get(seg, "words") or []) if str(_get(w, "word", "")).strip()]
        new: list[_Token] = []
        if words:
            # Whisper words carry their own leading space (" hello"); if a segment's words
            # have none at all, they come from elsewhere: space them unless CJK/Thai.
            spaced = any(str(_get(w, "word"))[:1].isspace() for w in words)
            for w in words:
                raw = str(_get(w, "word"))
                start = _get(w, "start")
                start = s_start if start is None else float(start)
                end = _get(w, "end")
                end = start if end is None else float(end)
                text = " ".join(raw.split())
                new.append(_Token(start, end, text, raw[:1].isspace() if spaced else None, False))
        else:
            text = _clean(str(_get(seg, "text", "") or ""))
            units = _units(text)
            weights = [max(1, _width(sep + unit)) for sep, unit in units]
            t, total = s_start, sum(weights)
            for (sep, unit), wgt in zip(units, weights):
                d = (s_end - s_start) * wgt / total
                new.append(_Token(t, t + d, unit, bool(sep), False))
                t += d
        if not new:
            continue
        new[0].seg_start = True
        for tok in new:
            prev = tokens[-1] if tokens else None
            if tok.space is None or (tok.seg_start and not tok.space):
                # Unknown spacing: a space unless either side is CJK / Thai.
                tok.space = bool(prev) and not (_no_space(prev.text[-1]) or _no_space(tok.text[0]))
            if prev:                                     # keep times monotonic
                tok.start = max(tok.start, prev.start)
            tok.end = max(tok.end, tok.start)
            tokens.append(tok)
    if tokens:
        tokens[0].space = False
    return tokens


def _join(tokens: list[_Token]) -> str:
    return "".join((" " if t.space and k else "") + t.text for k, t in enumerate(tokens))


class _CuePlanner:
    """Chooses where cues start and end: the cheapest split of the word tokens.

    Every possible cue (a run of tokens that fits the size and duration limits) gets a
    cost: a base cost (fewer, fuller cues), the quality of the break after it, reading
    speed, orphans, pauses inside it... Dynamic programming finds the cheapest split.
    """

    def __init__(self, toks: list[_Token], width: int, max_lines: int, max_duration: float,
                 min_duration: float, max_cps: float, min_gap: float):
        self.toks, self.n = toks, len(toks)
        self.width, self.max_lines = width, max_lines
        self.max_duration, self.min_duration = max_duration, min_duration
        self.max_cps, self.min_gap = max_cps, min_gap
        n = self.n
        # Gap and break class before each token k (between toks[k-1] and toks[k]).
        self.gap = [0.0] + [toks[k].start - toks[k - 1].end for k in range(1, n)]
        self.cls = [PLAIN] + [_break_class(toks[k - 1].text, toks[k].text) for k in range(1, n)]
        self.units = [_units(t.text) for t in toks]      # line-breaking units of each token

    def boundary_cost(self, k: int) -> float:
        """Cost of ending a cue before token k."""
        cls, gap = self.cls[k], self.gap[k]
        c = _CUE_BREAK_COST[cls]
        if cls != NOSPLIT:
            if gap >= 0.3:                               # a pause is a natural break
                c -= 34 if gap < 0.6 else 37 if gap < 1.0 else 40
            if self.toks[k].seg_start:                   # Whisper saw a boundary here
                c = min(c, 30)
        return max(c, 0)

    def fits(self, i: int, j: int, units: tuple, width: int) -> bool:
        """Does toks[i:j] fit the size and duration limits? (A single token always does.)"""
        if j - i == 1:
            return True
        return (width <= self.width * self.max_lines
                and self.toks[j - 1].end - self.toks[i].start <= self.max_duration
                and self.gap[j - 1] <= 2.0                # never show text over a long silence
                and _min_lines(units, self.width) <= self.max_lines)

    def cue_cost(self, i: int, j: int, units: tuple, width: int) -> float:
        """Cost of a cue made of toks[i:j] (excluding the break after it)."""
        toks, n, cls, gap = self.toks, self.n, self.cls, self.gap
        start, speech_end = toks[i].start, toks[j - 1].end
        next_start = toks[j].start if j < n else math.inf
        avail = max(min(next_start - self.min_gap, start + self.max_duration), speech_end) - start
        cost = 6.0                                       # fewer, fuller cues
        if j - i == 1 and n > 1 and not _no_space(toks[i].text[0]):
            cost += 80                                   # 1-word orphan (CJK tokens are characters)
        whole = (i == 0 or cls[i] == SENTENCE) and (j == n or cls[j] == SENTENCE)
        if width < 15 and not whole:
            cost += 12                                   # very short fragment
        cps = width / max(avail, 0.05)
        if cps > self.max_cps:
            cost += min(2 * (cps - self.max_cps), 60)    # too fast to read
        if avail < self.min_duration:
            cost += 15 * (self.min_duration - avail) + (30 if j - i == 1 else 0)
        for k in range(i + 1, j):
            if gap[k] > 0.7:
                cost += 20 * (gap[k] - 0.7)              # silence shown with text on screen
        if width > self.width:                           # quality of the line break
            cost += max(0.7 * _layout(units, self.width, self.max_lines)[1], -5)
        inner = [k for k in range(i + 1, j) if cls[k] == SENTENCE]
        cost += 12 * len(inner)                          # one sentence per cue reads best
        # A sentence starting at the very end (or a previous one ending at the very start)
        # of a cue reads badly: "...went well. And I" / "smoothly. Then we..."
        if inner:
            # Two sentences in one cue: each should get a line of its own.
            first, last = _join(toks[i:inner[0]]), _join(toks[inner[-1]:j])
            if len(inner) > 1 or max(_width(first), _width(last)) > self.width:
                cost += 15
            if j < n and cls[j] != SENTENCE and _width(last) < 20:
                cost += 12
            if i > 0 and cls[i] != SENTENCE and _width(first) < 20:
                cost += 8
        return cost

    def _add_token(self, units: list, k: int, first: bool) -> int:
        """Append token k's units to a cue's units (as _units() would split the joined
        text); return the width added."""
        tok_units = list(self.units[k])
        added = sum(_width(u) + len(sep) for sep, u in tok_units) - len(tok_units[0][0])
        sep = "" if first else (" " if self.toks[k].space else "")
        if not first and not sep and _glued(units[-1][1][-1], tok_units[0][1][0]):
            units[-1] = (units[-1][0], units[-1][1] + tok_units.pop(0)[1])
        elif tok_units:
            tok_units[0] = (sep, tok_units[0][1])
        units.extend(tok_units)
        return added + len(sep)

    def plan(self) -> list[tuple[int, int]]:
        """Return the cheapest split as (i, j) token ranges."""
        n = self.n
        best: list[tuple[float, int]] = [(0.0, n)] * (n + 1)   # best[i]: (cost, end) for toks[i:]
        for i in range(n - 1, -1, -1):
            options = []
            units: list[tuple[str, str]] = []
            width = 0
            for j in range(i + 1, n + 1):
                width += self._add_token(units, j - 1, first=j == i + 1)
                cue_units = tuple(units)
                if not self.fits(i, j, cue_units, width):
                    break                                # adding more words only gets worse
                c = self.cue_cost(i, j, cue_units, width) + (self.boundary_cost(j) if j < n else 0)
                options.append((c + best[j][0], j))
            best[i] = min(options)
        ranges, i = [], 0
        while i < n:
            ranges.append((i, best[i][1]))
            i = best[i][1]
        return ranges


def build_cues(segments: list[dict], max_chars_per_line: int = 42, max_lines: int = 2,
               max_duration: float = 6.0, min_duration: float = 1.0,
               max_cps: float = 17.0, min_gap: float = 0.08) -> list[Cue]:
    """Turn Whisper segments (ideally with word timestamps) into readable subtitle cues.

    Words of all segments are re-grouped into cues (see _CuePlanner), then times are
    adjusted for reading speed, minimum duration and gaps, and texts are wrapped.
    """
    toks = _tokens(segments)
    if not toks:
        return []
    planner = _CuePlanner(toks, max_chars_per_line, max_lines, max_duration,
                          min_duration, max_cps, min_gap)
    raw = [(toks[i].start, toks[j - 1].end, _join(toks[i:j])) for i, j in planner.plan()]
    cues = _time_cues(raw, max_duration, min_duration, max_cps, min_gap)
    for cue in cues:
        cue.text = wrap_text(cue.text, max_chars_per_line, max_lines)
    return cues


def _time_cues(raw, max_duration, min_duration, max_cps, min_gap) -> list[Cue]:
    """Final cue times from (speech_start, speech_end, text): reading time, gaps."""
    m = len(raw)
    starts = [r[0] for r in raw]
    ends = [r[1] for r in raw]
    needs = [min(max(min_duration, _width(r[2]) / max_cps), max_duration) for r in raw]
    for k in range(1, m):                                # overlapping word times
        starts[k] = max(starts[k], starts[k - 1] + 0.1)

    def limit(k: int) -> float:                          # latest end allowed by the next cue
        return starts[k + 1] - min_gap if k + 1 < m else math.inf

    # 1. Extend into the following silence for reading time / minimum duration.
    for k in range(m):
        ends[k] = max(ends[k], min(starts[k] + needs[k], limit(k)))
        ends[k] = min(ends[k], starts[k] + max_duration)  # even for one very long word
    # 2. Still too short: start up to 0.5 s earlier, in the silence before the cue.
    for k in range(m):
        short = needs[k] - (ends[k] - starts[k])
        if short > 0:
            earliest = ends[k - 1] + min_gap if k else 0.0
            starts[k] = max(min(starts[k], max(starts[k] - min(short, 0.5), earliest)), 0.0)
    # 3. Close small gaps (< 0.5 s) so subtitles don't flicker; enforce the minimum gap.
    for k in range(m):
        if k + 1 < m and limit(k) - ends[k] < 0.5 and limit(k) - starts[k] <= max_duration:
            ends[k] = max(ends[k], limit(k))
        ends[k] = max(min(ends[k], limit(k)), starts[k] + 0.1)
        if k + 1 < m:
            starts[k + 1] = max(starts[k + 1], ends[k] + min_gap)
    return [Cue(round(s, 3), round(e, 3), r[2]) for s, e, r in zip(starts, ends, raw)]


# --------------------------------------------------------------------------
# SRT / WebVTT
# --------------------------------------------------------------------------

def _timestamp(seconds: float, sep: str = ",") -> str:
    ms = max(0, int(round(seconds * 1000)))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def write_srt(cues: list[Cue], path: str, width: int = 42, max_lines: int = 2) -> None:
    """Write cues as SRT (UTF-8), re-wrapping each cue's text to `width`."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for i, cue in enumerate(cues, 1):
            f.write(f"{i}\n{_timestamp(cue.start)} --> {_timestamp(max(cue.end, cue.start))}\n")
            f.write(wrap_text(cue.text, width, max_lines) + "\n\n")


def _vtt_escape(text: str) -> str:
    text = re.sub(r"&(?!(?:amp|lt|gt|nbsp|lrm|rlm|#\d+|#x[0-9a-fA-F]+);)", "&amp;", text)
    text = re.sub(r"<(?!/?[ibu]>)", "&lt;", text)       # keep simple <i>/<b>/<u> tags
    return text.replace("-->", "→")


def write_vtt(cues: list[Cue], path: str, width: int = 42, max_lines: int = 2) -> None:
    """Write cues as WebVTT (UTF-8), re-wrapping each cue's text to `width`."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("WEBVTT\n\n")
        for cue in cues:
            f.write(f"{_timestamp(cue.start, '.')} --> {_timestamp(max(cue.end, cue.start), '.')}\n")
            f.write(_vtt_escape(wrap_text(cue.text, width, max_lines)) + "\n\n")


_TIME_LINE_RE = re.compile(
    r"^\s*(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:[,.](\d+))?\s*-+>\s*"
    r"(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:[,.](\d+))?")


def _parse_time(h, m, s, frac) -> float:
    ms = int((frac or "0")[:3].ljust(3, "0"))
    return int(h or 0) * 3600 + int(m) * 60 + int(s) + ms / 1000


def _read_text_file(path: str) -> str:
    with open(path, "rb") as f:
        data = f.read()
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1254", errors="replace")   # old Turkish / Western Windows files


def read_srt(path: str) -> list[Cue]:
    """Parse an SRT file robustly (BOM, CRLF, missing blank lines or indices, stray spaces).

    Each cue's text lines are stripped and joined with "\\n". A cue without text is kept
    (with text ""), so a cue emptied in the editor survives saving and reloading and the
    cues keep their numbers.
    """
    lines = _read_text_file(path).replace("\r\n", "\n").replace("\r", "\n").split("\n")
    timings = [(k, m) for k, m in ((k, _TIME_LINE_RE.match(line)) for k, line in enumerate(lines)) if m]
    cues = []
    for idx, (k, m) in enumerate(timings):
        stop = timings[idx + 1][0] if idx + 1 < len(timings) else len(lines)
        block = [line.strip() for line in lines[k + 1:stop]]
        while block and not block[-1]:
            block.pop()
        # The last line before the next timing line is the next cue's index number when it
        # follows a blank line or is the expected number; otherwise it is text ("2008").
        if (idx + 1 < len(timings) and block and block[-1].isdecimal()
                and ((len(block) > 1 and not block[-2]) or int(block[-1]) == idx + 2)):
            block.pop()
        text = [line for line in block if line]
        start = _parse_time(*m.group(1, 2, 3, 4))
        end = _parse_time(*m.group(5, 6, 7, 8))
        cues.append(Cue(start, max(end, start), "\n".join(text)))
    return cues
