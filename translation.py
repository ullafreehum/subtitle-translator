"""Subtitle translation: NLLB offline (default) and Google Translate online.

translate_texts() takes one text per subtitle cue and returns one translation
per cue. Cues often end mid-sentence, which translates badly, so consecutive
cues are joined into sentences, translated, and split back over the cues in
proportion to their original length (or, with return_groups=True, returned as
whole sentences for the caller to time as new subtitles).

Offline models: NLLB-200 distilled 1.3B (downloaded on first use) and, only where
it is installed, NLLB-200 3.3B ("nllb_large", see available_translators()).

Glossary terms are enforced by substituting them in the source text before
translating (keep terms as written, forced terms by their translation), then
restoring exact spelling in the output. If NLLB still drops a term, that
sentence is translated again with the term hidden behind a placeholder.
"""

from __future__ import annotations

import re
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from glossary import TermMap, contains_term, term_pattern

if TYPE_CHECKING:
    from glossary import Glossary

# --------------------------------------------------------------------------
# Public constants
# --------------------------------------------------------------------------

# Display name -> translator id accepted by translate_texts(translator=...).
# The translators every copy of the app has; available_translators() adds the
# large NLLB model where it is installed.
TRANSLATORS: dict[str, str] = {
    "Offline – NLLB (best, private, no limits)": "nllb",
    "Online – Google Translate": "online",
}
DEFAULT_TRANSLATOR = "nllb"

NLLB_REPO = "OpenNMT/nllb-200-distilled-1.3B-ct2-int8"
NLLB_DIR = Path(__file__).resolve().parent / "models" / "nllb-200-distilled-1.3B"

# NLLB-200 3.3B: better quality, about 4-5x slower (a 4 GB GPU holds it only partly); never downloaded by the app
# (installed only on the owner's PC with download_nllb_large(); CC-BY-NC licence).
NLLB_LARGE_REPO = "OpenNMT/nllb-200-3.3B-ct2-int8"
NLLB_LARGE_DIR = Path(__file__).resolve().parent / "models" / "nllb-200-3.3B"
NLLB_LARGE_NAME = "Offline – NLLB large model (best quality, slower)"


class Cancelled(Exception):
    """Raised when the user cancels a running job."""


class TranslationError(RuntimeError):
    """Raised when no translator could translate the texts."""


# Whisper code -> FLORES-200 code used by NLLB.
_FLORES = {
    "af": "afr_Latn", "am": "amh_Ethi", "ar": "arb_Arab", "as": "asm_Beng", "az": "azj_Latn",
    "ba": "bak_Cyrl", "be": "bel_Cyrl", "bg": "bul_Cyrl", "bn": "ben_Beng", "bo": "bod_Tibt",
    "bs": "bos_Latn", "ca": "cat_Latn", "cs": "ces_Latn", "cy": "cym_Latn", "da": "dan_Latn",
    "de": "deu_Latn", "el": "ell_Grek", "en": "eng_Latn", "es": "spa_Latn", "et": "est_Latn",
    "eu": "eus_Latn", "fa": "pes_Arab", "fi": "fin_Latn", "fo": "fao_Latn", "fr": "fra_Latn",
    "gl": "glg_Latn", "gu": "guj_Gujr", "ha": "hau_Latn", "he": "heb_Hebr", "hi": "hin_Deva",
    "hr": "hrv_Latn", "ht": "hat_Latn", "hu": "hun_Latn", "hy": "hye_Armn", "id": "ind_Latn",
    "is": "isl_Latn", "it": "ita_Latn", "ja": "jpn_Jpan", "jw": "jav_Latn", "ka": "kat_Geor",
    "kk": "kaz_Cyrl", "km": "khm_Khmr", "kn": "kan_Knda", "ko": "kor_Hang", "lb": "ltz_Latn",
    "ln": "lin_Latn", "lo": "lao_Laoo", "lt": "lit_Latn", "lv": "lvs_Latn", "mg": "plt_Latn",
    "mi": "mri_Latn", "mk": "mkd_Cyrl", "ml": "mal_Mlym", "mn": "khk_Cyrl", "mr": "mar_Deva",
    "ms": "zsm_Latn", "mt": "mlt_Latn", "my": "mya_Mymr", "ne": "npi_Deva", "nl": "nld_Latn",
    "nn": "nno_Latn", "no": "nob_Latn", "oc": "oci_Latn", "pa": "pan_Guru", "pl": "pol_Latn",
    "ps": "pbt_Arab", "pt": "por_Latn", "ro": "ron_Latn", "ru": "rus_Cyrl", "sa": "san_Deva",
    "sd": "snd_Arab", "si": "sin_Sinh", "sk": "slk_Latn", "sl": "slv_Latn", "sn": "sna_Latn",
    "so": "som_Latn", "sq": "als_Latn", "sr": "srp_Cyrl", "su": "sun_Latn", "sv": "swe_Latn",
    "sw": "swh_Latn", "ta": "tam_Taml", "te": "tel_Telu", "tg": "tgk_Cyrl", "th": "tha_Thai",
    "tk": "tuk_Latn", "tl": "tgl_Latn", "tr": "tur_Latn", "tt": "tat_Cyrl", "uk": "ukr_Cyrl",
    "ur": "urd_Arab", "uz": "uzn_Latn", "vi": "vie_Latn", "yi": "ydd_Hebr", "yo": "yor_Latn",
    "yue": "yue_Hant", "zh": "zho_Hans",
}

# Whisper code -> Google Translate code, where they differ.
_GOOGLE_CODE_MAP = {"zh": "zh-CN", "he": "iw", "jw": "jw"}

MAX_CHARS_PER_REQUEST = 4500   # Google
MYMEMORY_MAX_CHARS = 450       # MyMemory accepts ~500 characters per request
NLLB_BATCH = 64                # sentences per GPU batch and progress/cancel step
NLLB_CPU_BATCH = 8             # the same on the CPU
NLLB_LARGE_BATCH = 16          # the large model on the GPU (4 GB card: little memory left)

_NO_SPACE_LANGS = {"zh", "ja", "th", "yue", "lo", "km", "my"}
_APOSTROPHE_LANGS = {"tr", "az"}  # proper nouns take suffixes after an apostrophe

Log = Callable[[str], None]


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _one_line(error: BaseException) -> str:
    """Error text on one line (Windows/CUDA messages can span several lines)."""
    return " ".join(str(error).split())


def _check_cancel(cancel: threading.Event | None) -> None:
    if cancel is not None and cancel.is_set():
        raise Cancelled("Cancelled by user.")


def _base_code(code: str | None) -> str | None:
    """Normalise a code for comparison ('zh-CN' -> 'zh', 'iw' -> 'he')."""
    if not code:
        return None
    code = code.lower()
    if code == "iw":
        return "he"
    return code.split("-")[0]


def _google_code(code: str) -> str:
    return _GOOGLE_CODE_MAP.get(code, code)


def _capitalize(text: str, lang: str) -> str:
    """Upper-case the first letter (Turkish: i -> İ, ı -> I)."""
    first = text[:1]
    if lang in _APOSTROPHE_LANGS:
        first = {"i": "İ", "ı": "I"}.get(first, first.upper())
    return first.upper() + text[1:]


# --------------------------------------------------------------------------
# Glossary enforcement
# --------------------------------------------------------------------------

_PLACEHOLDER = re.compile(r"\bZX ?(\d+)", re.IGNORECASE)

_TR_VOWELS = "aeıioöuü"
_TR_BACK = "aıou"
_TR_ROUND = "ouöü"
_TR_VOICELESS = "fstkçşhp"
_TR_SOFTEN = {"ç": "c", "k": "ğ", "p": "b"}
_TR_BOZUKLUK = re.compile(r"(?<=\w )bozukluk(?= (?:olan|olanlar|olduğu|olduğunu|var|yok)\b)")
# Loanwords whose suffixes take front vowels despite a back last vowel.
_TR_FRONT_LOANS = ("kontrol", "protokol", "sembol", "rol", "alkol", "hayal", "saat", "kalp", "ideal")


def _tr_suffix(word: str, suffix: str) -> str:
    """Re-attach a Turkish suffix to `word` with correct vowel harmony and buffer letters.

    pekiştireç + i -> pekiştireci, öz düzenleme + ü -> öz düzenlemeyi,
    iletişim çemberleri + yi -> iletişim çemberlerini, hedef davranış + den -> hedef davranıştan.
    """
    low = word.lower()
    vowels = [c for c in low if c in _TR_VOWELS]
    if not vowels or not suffix.isalpha():
        return word + suffix
    prev = vowels[-1]
    if low.split()[-1].endswith(_TR_FRONT_LOANS):  # kontrol -> kontrolü, saat -> saati
        prev = {"a": "e", "o": "ö", "u": "ü", "ı": "i"}.get(prev, prev)
    sfx = []
    for ch in suffix.lower():
        if ch in "ae":
            ch = "a" if prev in _TR_BACK else "e"
        elif ch in "ıiuü":
            ch = {(True, False): "ı", (True, True): "u",
                  (False, False): "i", (False, True): "ü"}[(prev in _TR_BACK, prev in _TR_ROUND)]
        if ch in _TR_VOWELS:
            prev = ch
        sfx.append(ch)
    s = "".join(sfx)
    s = re.sub(r"^(y[aeıiuü])\1", r"\1", s)  # repeated buffer syllable: sandalye + yeye -> sandalyeye
    if suffix.lower().endswith("ki"):  # "-ki" never changes: odasındaki
        s = s[:-2] + "ki"
    last = low[-1]
    # A compound ending in a possessive ("oyun odası", "iletişim çemberleri")
    # takes "n" before case endings; other vowel-final words take "y".
    # Loanwords ending in a vowel (terapi, ekolali, psikoloji...) are not possessives.
    possessive = (" " in word.strip() and low[-1] in "ıiuü"
                  and re.search(r"(?:terapi|pati|pleji|lali|leksi|praksi|fazi|loji|metri|grafi|skopi|fobi|mani)$",
                                low) is None)
    if possessive and re.fullmatch(r"n[ıiuü](?:m|n|m[ıiuü]z|n[ıiuü]z)", s):
        # A personal ending replaces the compound's own: vaka yükü + nüm -> vaka yüküm.
        return word + s[2:]
    if last in _TR_VOWELS:
        if s[0] in _TR_VOWELS:
            s = ("n" if possessive else "y") + s
        elif possessive and s[0] == "y" and len(s) > 1 and s[1] in _TR_VOWELS:
            s = "n" + s[1:]
    elif s[0] in "yn" and len(s) > 1 and s[1] in _TR_VOWELS:
        s = s[1:]  # no buffer letter after a consonant: kontrol + yü -> kontrolü, otizm + nin -> otizmin
        if len(vowels) > 1 and last in _TR_SOFTEN:
            word = word[:-1] + _TR_SOFTEN[last]
    elif s[0] in _TR_VOWELS:
        if len(vowels) > 1 and last in _TR_SOFTEN:  # consonant softening (not in one-syllable words)
            word = word[:-1] + _TR_SOFTEN[last]
    elif s[0] in "dt" and len(s) > 1 and s[1] in _TR_VOWELS:
        s = ("t" if last in _TR_VOICELESS else "d") + s[1:]
    return word + s


class _Terms:
    """Glossary rules for one language pair."""

    def __init__(self, glossary: Glossary | None, source: str | None, target: str):
        keep = list(glossary.keep_terms) if glossary else []
        forced = glossary.translations(source or "", target) if glossary else {}
        self.target = target
        self.forced_values = set(forced.values())
        # Source side: keep terms normalised to their exact spelling, forced
        # terms replaced by their translation (the model keeps them as is).
        self.source_map = TermMap({**{t: t for t in keep}, **forced})
        # Turkish glues suffixes to words ("filial terapide"), so forced Turkish
        # terms also match with a suffix, which stays after an apostrophe
        # ("filial therapy'de"); the model then translates the suffix.
        if source == "tr" and forced:
            self.source_map = TermMap({t: t for t in keep})
            self.suffix_map = TermMap(forced, suffixes=True)
        else:
            self.suffix_map = None
        # The terms that must appear in the output, as found in prepared text.
        self.wanted_map = TermMap({v: v for v in [*keep, *forced.values()]})
        # Output side: exact spelling for keep terms and for forced
        # translations that are not plain lower case (e.g. "DEHB", "ADHD").
        self.output_map = TermMap({**{t: t for t in keep},
                                   **{v: v for v in forced.values() if v != v.lower()}})
        # Turkish: the model may treat a forced common noun as a proper noun
        # ("Kursiyerler'in"); such words take suffixes without an apostrophe.
        common = [v for v in forced.values() if v == v.lower()] if target in _APOSTROPHE_LANGS else []
        self.apostrophe = (re.compile(r"(?<!\w)(" + "|".join(map(term_pattern, common)) + r")['’](\w+)",
                                      re.IGNORECASE) if common else None)
        # Turkish: the model glues suffixes to a forced term without vowel harmony
        # ("pekiştireçi", "öz düzenlemeü"); _tr_suffix() repairs them.
        common = sorted(common, key=len, reverse=True) if target == "tr" else []
        self.suffixed = (re.compile(r"(?<!\w)(" + "|".join(map(term_pattern, common)) + r")(\w+)",
                                    re.IGNORECASE) if common else None)

    def prepare(self, text: str) -> str:
        # Forced terms go in as written. A capital at the start of a sentence is
        # restored on the translation instead, because the model often moves the
        # term away from the start ("Vaka yükümüz…" -> "We have too much caseload").
        text = self.source_map.sub(text)
        return self.suffix_map.sub(text) if self.suffix_map is not None else text

    def finish(self, text: str) -> str:
        text = self.output_map.sub(text)
        if self.apostrophe is not None:
            text = self.apostrophe.sub(r"\1\2", text)
        if self.suffixed is not None:
            text = self.suffixed.sub(lambda m: _tr_suffix(m.group(1), m.group(2)), text)
        if self.target == "tr":
            # A forced "... bozukluk" before "olan" needs the compound ending: "panik bozukluğu olan".
            text = _TR_BOZUKLUK.sub("bozukluğu", text)
        return text

    def missing(self, prepared: str, output: str) -> int:
        """How many glossary terms of a prepared source text are absent from `output`."""
        return sum(not contains_term(output, t) for t in set(self.wanted_map.find(prepared)))

    def protect(self, prepared: str) -> tuple[str, list[str]]:
        """Replace glossary terms with placeholders ZX1, ZX2... (the model copies them)."""
        values: list[str] = []

        def repl(value: str, _matched: str) -> str:
            if value not in values:
                values.append(value)
            return f"ZX{values.index(value) + 1}"

        return self.wanted_map.sub(prepared, repl), values

    @staticmethod
    def restore(text: str, values: list[str]) -> str:
        """Put the terms back in place of the placeholders (finish() fixes apostrophes)."""
        def repl(m: re.Match) -> str:
            n = int(m.group(1))
            return values[n - 1] if 0 < n <= len(values) else ""

        return _PLACEHOLDER.sub(repl, text)


# --------------------------------------------------------------------------
# Sentence grouping
# --------------------------------------------------------------------------
# Translate whole sentences, then split each translation back over its cues
# in proportion to their original length.

_SENTENCE_END = (".", "?", "!", "…", "。", "？", "！", '"', "”")


def _sentence_groups(texts: list[str], max_segments: int = 3, max_chars: int = 200) -> list[list[int]]:
    """Indices of consecutive texts forming sentences; empty texts belong to no group."""
    groups: list[list[int]] = []
    current: list[int] = []
    size = 0
    for i, t in enumerate(texts):
        if not t.strip():   # an empty cue must not receive part of its neighbour's translation
            continue
        current.append(i)
        size += len(t)
        if t.rstrip().endswith(_SENTENCE_END) or len(current) >= max_segments or size >= max_chars:
            groups.append(current)
            current, size = [], 0
    if current:
        groups.append(current)
    return groups


def _split_like(text: str, lengths: list[int], no_spaces: bool) -> list[str]:
    """Split text into len(lengths) pieces with roughly the same proportions."""
    n = len(lengths)
    if n == 1:
        return [text]
    units = list(text) if no_spaces else text.split()
    sep = "" if no_spaces else " "
    if len(units) < n:
        return units + ["..."] * (n - len(units))
    # Character offset at the end of each unit.
    ends, pos = [], 0
    for u in units:
        pos += len(u) + len(sep)
        ends.append(pos)
    total_src, total = sum(lengths) or 1, ends[-1]

    cuts, prev, acc = [], 0, 0
    for k in range(n - 1):
        acc += lengths[k]
        want = acc / total_src
        best, best_score = None, None
        # Leave at least one unit for every remaining piece.
        for j in range(prev + 1, len(units) - (n - 1 - k) + 1):
            score = abs(ends[j - 1] / total - want)
            if units[j - 1].endswith((",", ".", ";", ":", "?", "!", "，", "、", "。")):
                score -= 0.05  # prefer cutting after punctuation
            if best_score is None or score < best_score:
                best, best_score = j, score
        cuts.append(best)
        prev = best
    bounds = [0] + cuts + [len(units)]
    return [sep.join(units[a:b]) for a, b in zip(bounds, bounds[1:])]


# NLLB was trained on single sentences and tends to drop the second sentence
# of a multi-sentence input, so it gets one sentence at a time.
_SPLIT_POINT = re.compile(r"(?<=[.!?…])\s+(?=\S)|(?<=[。！？])")
_ABBREVIATIONS = {"dr.", "mr.", "mrs.", "ms.", "prof.", "st.", "vs.", "e.g.", "i.e.", "etc.", "no."}


def _split_sentences(text: str) -> list[str]:
    out: list[str] = []
    for piece in _SPLIT_POINT.split(text):
        piece = piece.strip()
        if not piece:
            continue
        if out and out[-1].rsplit(None, 1)[-1].lower() in _ABBREVIATIONS:
            out[-1] += " " + piece
        else:
            out.append(piece)
    return out


_DIALOGUE_DASH = re.compile(r"[-–]\s")


def _clean_output(source: str, output: str) -> str:
    """NLLB (trained partly on movie subtitles) sometimes turns a short line into
    a dialogue or repeats it: "Thank you." -> "- Teşekkür ederim. - Evet." or
    "Teşekkür ederim. Teşekkürler." Keep only the first part then."""
    output = output.strip()
    # A dialogue dash is followed by a space; "-5 derece" starts with a minus sign.
    if _DIALOGUE_DASH.match(output) and not _DIALOGUE_DASH.match(source.lstrip()):
        output = re.split(r"\s+[-–]\s+", output[1:].lstrip(), maxsplit=1)[0]
    if len(source.split()) <= 4:
        output = _split_sentences(output)[0] if output else output
    return output.strip()


_SPACE_BEFORE = re.compile(r"(?<=\S) +([,.;:!?])(?=\s|$)")
_SPACE_BEFORE_FR = re.compile(r"(?<=\S) +([,.])(?=\s|$)")      # French keeps "Oui !"
_SPLIT_CONTRACTION = re.compile(r"(?<=\w) '(s|re|ve|ll|d|m|t)\b")


def _fix_spacing(text: str, lang: str) -> str:
    """NLLB sometimes spaces out punctuation like tokenized text: "warn . It 's" -> "warn. It's"."""
    text = (_SPACE_BEFORE_FR if lang == "fr" else _SPACE_BEFORE).sub(r"\1", text)
    return _SPLIT_CONTRACTION.sub(r"'\1", text) if lang == "en" else text


_CJK_BEFORE = re.compile(r"(?<=[぀-ヿ㐀-䶿一-鿿])[,.?!:;]")
_CJK_PUNCT = {",": "，", ".": "。", "?": "？", "!": "！", ":": "：", ";": "；"}


def _cjk_punctuation(text: str, lang: str) -> str:
    """NLLB writes ASCII punctuation in Chinese/Japanese ("大家早上好."): use the full-width forms."""
    marks = {**_CJK_PUNCT, ",": "、"} if lang == "ja" else _CJK_PUNCT
    return _CJK_BEFORE.sub(lambda m: marks[m.group()], text)


# --------------------------------------------------------------------------
# Online: Google Translate, MyMemory as backup
# --------------------------------------------------------------------------

def _with_retry(func, *args, attempts: int = 3):
    last = None
    for i in range(attempts):
        try:
            return func(*args)
        except Exception as e:  # noqa: BLE001
            last = e
            if i < attempts - 1:
                time.sleep(1.5 * (i + 1))
    raise RuntimeError(_short_reason(last))


def _short_reason(e: Exception | None) -> str:
    """A short, readable reason for a failed online request (for the log)."""
    text = " ".join(str(e).split())
    low = f"{type(e).__name__} {text}".lower()
    if "too many requests" in low or "toomanyrequests" in low or "429" in low:
        return "too many requests; the service limits how much one computer can translate"
    if any(k in low for k in ("connection", "timed out", "timeout", "getaddrinfo", "resolve")):
        return "no connection to the service; is the internet on?"
    return text[:120] or type(e).__name__


def _make_google(source: str | None, target: str):
    from deep_translator import GoogleTranslator

    tgt = _google_code(target)
    if source:
        try:
            return GoogleTranslator(source=_google_code(source), target=tgt)
        except Exception:  # noqa: BLE001  (source not supported by Google)
            pass
    return GoogleTranslator(source="auto", target=tgt)


def _mymemory_code(code: str) -> str:
    """MyMemory wants locale codes like 'tr-TR'; map a base code onto one."""
    from deep_translator import MyMemoryTranslator

    supported = MyMemoryTranslator(source="en-GB", target="tr-TR").get_supported_languages(as_dict=True)
    g = _google_code(code)
    for c in supported.values():
        if c.lower() == g.lower() or c.lower().startswith(code.lower() + "-"):
            return c
    return code


def _make_mymemory(source: str | None, target: str):
    from deep_translator import MyMemoryTranslator

    return MyMemoryTranslator(source=_mymemory_code(source or "en"), target=_mymemory_code(target))


def _chunk(texts: list[str], indices: list[int], max_chars: int) -> list[list[int]]:
    """Group line indices into chunks whose joined text stays under max_chars."""
    chunks: list[list[int]] = []
    current: list[int] = []
    size = 0
    for i in indices:
        t = texts[i]
        if current and size + len(t) + 1 > max_chars:
            chunks.append(current)
            current, size = [], 0
        current.append(i)
        size += len(t) + 1
    if current:
        chunks.append(current)
    return chunks


def _translate_chunk(translator, lines: list[str], n: int, log: Log, cancel) -> list[str]:
    translated = _with_retry(translator.translate, "\n".join(lines)) or ""
    if "MYMEMORY WARNING" in translated.upper():  # daily free quota used up
        raise RuntimeError("MyMemory daily limit reached")
    parts = [p.strip() for p in translated.split("\n")]
    if len(parts) != len(lines):
        log(f"Batch {n}: line count mismatch ({len(parts)} vs {len(lines)}), translating line by line.")
        parts = []
        for line in lines:
            _check_cancel(cancel)
            parts.append((_with_retry(translator.translate, line) or line).strip())
    return parts


def _online_translate(texts: list[str], source: str | None, target: str,
                      log: Log, progress, cancel) -> list[str]:
    """Translate with Google Translate, switching to MyMemory if Google refuses
    (e.g. rate limit). Raises RuntimeError if both fail."""
    translator = _make_google(source, target)
    chunks = _chunk(texts, list(range(len(texts))), MAX_CHARS_PER_REQUEST)
    using_fallback = False

    result = list(texts)
    done = 0
    for n, idx in enumerate(chunks, 1):
        _check_cancel(cancel)
        parts = None
        if not using_fallback:
            try:
                parts = _translate_chunk(translator, [texts[i] for i in idx], n, log, cancel)
            except RuntimeError as e:
                log(f"Google Translate is not available ({e}). Switching to MyMemory (another online translator).")
                translator = _make_mymemory(source, target)
                using_fallback = True
        if parts is None:
            parts = []
            for sub in _chunk(texts, idx, MYMEMORY_MAX_CHARS):
                _check_cancel(cancel)
                parts += _translate_chunk(translator, [texts[i] for i in sub], n, log, cancel)
        for i, p in zip(idx, parts):
            result[i] = p or texts[i]
        done += len(idx)
        log(f"Translated batch {n}/{len(chunks)}.")
        progress(done / len(texts))
    return result


# --------------------------------------------------------------------------
# Offline: NLLB-200 (CTranslate2)
# --------------------------------------------------------------------------

_nllb_lock = threading.Lock()
_nllb: dict[str, dict] = {}  # model id -> {"tokenizer", "translator", "device"} once loaded
_nllb_cpu_only = False       # force the CPU for every model (tests: --cpu)
_gpu_failed: set[str] = set()  # models that failed on the GPU; free_gpu_models() lets them retry

# Model id -> where it lives and how to run it.
_NLLB_MODELS = {
    "nllb": {"repo": NLLB_REPO, "dir": NLLB_DIR, "size": "about 1.3 GB", "label": "NLLB",
             "gpu_batch": NLLB_BATCH},
    "nllb_large": {"repo": NLLB_LARGE_REPO, "dir": NLLB_LARGE_DIR, "size": "about 3.3 GB",
                   "label": "NLLB large", "gpu_batch": NLLB_LARGE_BATCH},
}
_TRANSLATOR_IDS = {*TRANSLATORS.values(), "nllb_large"}   # every id translate_texts() accepts
_MODEL_FILES = ("model.bin", "config.json", "shared_vocabulary.json", "tokenizer.json")


def _model_complete(path: Path) -> bool:
    """All model files there (the downloader writes model.bin under its final name only when done)."""
    return all((path / name).is_file() and (path / name).stat().st_size > 0 for name in _MODEL_FILES)


def available_translators() -> dict[str, str]:
    """TRANSLATORS plus the large NLLB model when it is installed (display name -> id)."""
    names: dict[str, str] = {}
    for name, tid in TRANSLATORS.items():
        names[name] = tid
        if tid == "nllb" and _model_complete(NLLB_LARGE_DIR):
            names[NLLB_LARGE_NAME] = "nllb_large"
    return names


def free_gpu_models() -> None:
    """Release the cached NLLB translators (GPU and CPU memory); the next translation loads
    its model again and may try the GPU again. engine.py frees Whisper the same way
    before the large model, which only fits on a 4 GB card alone."""
    import gc

    with _nllb_lock:
        for m in _nllb.values():
            try:
                m["translator"].unload_model()  # frees the memory now, not at garbage collection
            except Exception:  # noqa: BLE001
                pass
        _nllb.clear()
        _gpu_failed.clear()
    gc.collect()


def download_nllb_large(log: Log = print) -> Path:
    """Download the large NLLB model into models/nllb-200-3.3B (called by hand, once;
    the app never downloads it). Returns the model folder."""
    if _model_complete(NLLB_LARGE_DIR):
        log(f"The large translation model is already installed in {NLLB_LARGE_DIR}.")
        return NLLB_LARGE_DIR
    from huggingface_hub import snapshot_download

    log("Downloading the large offline translation model (about 3.3 GB)...")
    with download_status("the large translation model", "about 3.3 GB", log):
        snapshot_download(repo_id=NLLB_LARGE_REPO, local_dir=str(NLLB_LARGE_DIR))
    if not _model_complete(NLLB_LARGE_DIR):
        raise TranslationError(f"The download of {NLLB_LARGE_REPO} is incomplete.")
    log(f"Large offline translation model downloaded into {NLLB_LARGE_DIR}.")
    return NLLB_LARGE_DIR


@contextmanager
def download_status(what: str, size: str, log: Log, every: float = 30.0):
    """While a model downloads, say every few seconds that it is still going: a first run
    can spend many minutes here and must not look frozen. (The downloader writes into
    several cache folders, so the bytes so far can't be counted reliably.)
    Also used by engine.py for Whisper."""
    if sys.stderr is None:
        # No console (GUI started with pythonw): the download progress bars would crash.
        from huggingface_hub.utils import disable_progress_bars
        disable_progress_bars()
    start, stop = time.time(), threading.Event()

    def report() -> None:
        while not stop.wait(every):
            minutes = int(time.time() - start) // 60
            elapsed = f"{minutes} min" if minutes else f"{int(time.time() - start)} s"
            log(f"  still downloading {what} ({size}), {elapsed} so far. Please wait...")

    watcher = threading.Thread(target=report, daemon=True)
    watcher.start()
    try:
        yield
    finally:
        stop.set()
        watcher.join()


def _ensure_nllb_model(log: Log, model: str = "nllb") -> Path:
    """Download the NLLB model into models/ the first time (the large model is never downloaded here)."""
    if model != "nllb":
        path = _NLLB_MODELS[model]["dir"]
        if not _model_complete(path):
            raise TranslationError(f"The large offline translation model is not installed ({path}).")
        return path
    needed = _MODEL_FILES
    if all((NLLB_DIR / name).is_file() for name in needed):   # all there: an earlier download finished
        return NLLB_DIR
    from huggingface_hub import snapshot_download

    log("Downloading the offline translation model (about 1.3 GB, only once). "
        "This can take several minutes...")
    try:
        with download_status("the translation model", "about 1.3 GB", log):
            snapshot_download(repo_id=NLLB_REPO, local_dir=str(NLLB_DIR))
    except Exception as e:  # noqa: BLE001
        raise TranslationError("Could not download the offline translation model (no internet?).\n"
                               "The internet is needed only the first time. Check it and try again.\n"
                               f"{type(e).__name__}: {e}") from e
    log("Offline translation model downloaded.")
    return NLLB_DIR


def _release(model: str) -> None:
    """Drop one cached translator and free its memory now (caller holds _nllb_lock)."""
    m = _nllb.pop(model, None)
    if m is not None:
        try:
            m["translator"].unload_model()
        except Exception:  # noqa: BLE001
            pass


def _load_nllb(log: Log, model: str = "nllb") -> dict:
    """Load (once) an NLLB tokenizer and translator, on the GPU if possible."""
    with _nllb_lock:
        if model in _nllb:
            return _nllb[model]
        import ctranslate2
        import tokenizers

        from cuda_setup import cuda_usable

        spec = _NLLB_MODELS[model]
        label = spec["label"]
        path = _ensure_nllb_model(log, model)
        tokenizer = tokenizers.Tokenizer.from_file(str(path / "tokenizer.json"))
        translator = None
        if not _nllb_cpu_only and model not in _gpu_failed and cuda_usable(log):
            # Only one NLLB model on the GPU at a time (both do not fit on a 4 GB card).
            for other in [m for m, v in _nllb.items() if v["device"] == "cuda"]:
                _release(other)
            try:
                log(f"Loading offline translation model ({label}) on GPU...")
                translator = ctranslate2.Translator(str(path), device="cuda", compute_type="int8_float16")
            except Exception as e:  # noqa: BLE001
                _gpu_failed.add(model)
                hint = " (not enough GPU memory?)" if model == "nllb_large" else ""
                log(f"Could not load {label} on GPU{hint} ({_one_line(e)}). Using CPU"
                    + (", which is much slower." if model == "nllb_large" else "."))
        if translator is None:
            log(f"Loading offline translation model ({label}) on CPU...")
            translator = ctranslate2.Translator(str(path), device="cpu", compute_type="int8")
        _nllb[model] = {"tokenizer": tokenizer, "translator": translator, "device": translator.device}
        return _nllb[model]


def _nllb_batch(sentences: list[str], src: str, tgt: str, log: Log, model: str = "nllb") -> list[str]:
    """Translate a list of single sentences (FLORES codes); falls back to CPU on GPU errors."""
    loaded = _load_nllb(log, model)
    tok = loaded["tokenizer"]
    tokens = [[src] + tok.encode(s, add_special_tokens=False).tokens + ["</s>"] for s in sentences]
    batch = _NLLB_MODELS[model]["gpu_batch"] if loaded["device"] == "cuda" else NLLB_BATCH
    try:
        results = loaded["translator"].translate_batch(
            tokens, target_prefix=[[tgt]] * len(tokens), beam_size=4, max_batch_size=batch)
    except Exception as e:  # noqa: BLE001
        if loaded["device"] != "cuda":
            raise
        # Typically out of GPU memory (the Whisper model may still be loaded).
        log(f"Translation on GPU failed ({_one_line(e)}). Switching to CPU.")
        with _nllb_lock:
            _release(model)
            _gpu_failed.add(model)
        return _nllb_batch(sentences, src, tgt, log, model)
    return [_clean_output(s, tok.decode([tok.token_to_id(t) for t in r.hypotheses[0][1:]],
                                        skip_special_tokens=True))
            for s, r in zip(sentences, results)]


def _nllb_translate(texts: list[str], source: str | None, target: str, terms: _Terms,
                    log: Log, progress, cancel, model: str = "nllb") -> list[str]:
    """Translate texts with NLLB, one sentence at a time, applying the glossary."""
    src, tgt = _FLORES.get(source or ""), _FLORES.get(target)
    if not src or not tgt:
        if not src:
            raise TranslationError(f"Offline translation does not support the spoken language '{source}'.\n"
                                   "If that language is wrong, choose the spoken language instead "
                                   "of Auto-detect; otherwise use the online translator.")
        raise TranslationError(f"Offline translation does not support language '{target}'.\n"
                               "Use the online translator for this language.")
    try:
        tokenizer = _load_nllb(log, model)["tokenizer"]
    except TranslationError:
        raise
    except Exception as e:  # noqa: BLE001
        raise TranslationError(f"Could not load the offline translation model: {e}") from e
    # An unknown language token would silently give garbage, never a translation.
    for code in (src, tgt):
        if tokenizer.token_to_id(code) is None:
            raise TranslationError(f"The offline translator has no language code '{code}'.")

    # Flatten texts into sentences, remembering which text each belongs to.
    raw: list[str] = []
    sentences: list[str] = []  # with the glossary applied
    owner: list[int] = []
    for i, t in enumerate(texts):
        for s in _split_sentences(t):
            raw.append(s)
            sentences.append(terms.prepare(s))
            owner.append(i)

    # Big batches are fastest on the GPU; on the CPU they gain little, and smaller ones
    # keep the progress bar moving and cancel quick.
    on_gpu = _nllb.get(model, {}).get("device") == "cuda"
    step = _NLLB_MODELS[model]["gpu_batch"] if on_gpu else NLLB_CPU_BATCH

    def run(batch_sentences: list[str], share: float, start_at: float) -> list[str]:
        done: list[str] = []
        for start in range(0, len(batch_sentences), step):
            _check_cancel(cancel)
            try:
                done += _nllb_batch(batch_sentences[start:start + step], src, tgt, log, model)
            except Exception as e:  # noqa: BLE001
                raise TranslationError(f"Offline translation failed: {e}") from e
            progress(start_at + share * len(done) / max(1, len(batch_sentences)))
        return done

    # Forced terms put target-language words into the source sentence, which can
    # confuse the model (mostly Turkish -> English). Sentences the glossary changed
    # are also translated unchanged; the version with more glossary terms wins,
    # and a tie keeps the unchanged one.
    changed = [k for k, (r, s) in enumerate(zip(raw, sentences)) if r != s]
    share = 0.95 * len(sentences) / max(1, len(sentences) + len(changed))
    out = run(sentences, share, 0.0)
    if changed:
        plain = run([raw[k] for k in changed], 0.95 - share, share)
        for k, p in zip(changed, plain):
            if terms.missing(sentences[k], p) <= terms.missing(sentences[k], out[k]):
                out[k] = p

    # Retry sentences where the model dropped a glossary term, with the
    # terms replaced by placeholders it copies verbatim.
    retry = [k for k, (s, o) in enumerate(zip(sentences, out)) if terms.missing(s, o)]
    if retry:
        _check_cancel(cancel)
        protected = [terms.protect(sentences[k]) for k in retry]
        try:
            second = _nllb_batch([p for p, _ in protected], src, tgt, log, model)
        except Exception as e:  # noqa: BLE001
            raise TranslationError(f"Offline translation failed: {e}") from e
        for k, (_, values), o in zip(retry, protected, second):
            candidate = terms.restore(o, values)
            if terms.missing(sentences[k], candidate) < terms.missing(sentences[k], out[k]):
                out[k] = candidate
    progress(1.0)
    out = [_fix_spacing(o, target) for o in out]
    # A sentence that starts with a capital keeps one (a forced term at the start
    # can make the model begin in lower case: "multidisipliner ekipte...").
    out = [_capitalize(o, target) if r[:1].isupper() and o[:1].islower() else o
           for r, o in zip(raw, out)]
    if target in ("zh", "ja", "yue"):
        out = [_cjk_punctuation(o, target) for o in out]

    sep = "" if target in _NO_SPACE_LANGS else " "
    joined: list[list[str]] = [[] for _ in texts]
    for i, o in zip(owner, out):
        joined[i].append(o.strip())
    return [sep.join(parts) for parts in joined]


def _dropped_content(sources: list[str], outputs: list[str]) -> list[int]:
    """Indices of long texts whose translation is less than half as long as is usual for
    this text (the length ratio depends on the languages, e.g. English -> Chinese ~0.3)."""
    ratios = sorted(len(o) / len(s) for s, o in zip(sources, outputs) if len(s) >= 20)
    if not ratios:
        return []
    typical = ratios[len(ratios) // 2]
    return [k for k, (s, o) in enumerate(zip(sources, outputs))
            if len(s) >= 60 and len(o) < 0.5 * typical * len(s)]


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------

def translate_texts(texts: list[str], source: str, target: str,
                    translator: str = DEFAULT_TRANSLATOR,
                    glossary: Glossary | None = None,
                    log: Log = print,
                    progress: Callable[[float], None] = lambda p: None,
                    cancel: threading.Event | None = None,
                    return_groups: bool = False) -> list[str] | list[tuple[list[int], str]]:
    """Translate one text per subtitle cue; returns one translation per cue.

    translator: "nllb" (offline), "nllb_large" (offline, where installed: see
    available_translators()) or "online" (Google -> MyMemory -> NLLB).
    return_groups: instead return [(cue indices, translation of the whole sentence group)]
    in cue order, for re-timing the translation as new subtitles; empty cues are in no group.
    Raises Cancelled when `cancel` is set, TranslationError if every translator failed.
    """
    if translator not in _TRANSLATOR_IDS:
        raise ValueError(f"Unknown translator: {translator!r}")
    if translator == "nllb_large" and not _model_complete(NLLB_LARGE_DIR):
        log(f"The large offline translation model is not installed ({NLLB_LARGE_DIR}). "
            "Using the standard offline model (NLLB).")
        translator = "nllb"
    source, target = _base_code(source), _base_code(target)
    if not target:
        raise ValueError("A target language is required.")
    terms = _Terms(glossary, source, target)
    if not texts:
        return []
    sep = "" if target in _NO_SPACE_LANGS else " "
    if source == target:
        progress(1.0)
        if return_groups:
            return [(g, terms.finish(sep.join(" ".join(texts[i].split()) for i in g)))
                    for g in _sentence_groups(texts)]
        return [terms.finish(t) for t in texts]

    groups = _sentence_groups(texts)
    # Collapse line breaks/whitespace inside cues; apply glossary to the source
    # (NLLB applies it itself, sentence by sentence).
    raw = [" ".join(" ".join(texts[i].split()) for i in g) for g in groups]
    todo = [k for k, s in enumerate(raw) if s]  # skip empty groups
    todo_raw = [raw[k] for k in todo]
    todo_texts = [terms.prepare(s) for s in todo_raw]
    log(f"Translating {len(texts)} subtitles ({len(todo_texts)} sentences), {source} -> {target}.")

    _check_cancel(cancel)
    model = "nllb_large" if translator == "nllb_large" else "nllb"   # also the online fallback
    used_nllb = translator != "online"
    if translator == "online":
        try:
            translated = _online_translate(todo_texts, source, target, log, progress, cancel)
        except Cancelled:
            raise
        except Exception as e:  # noqa: BLE001
            log(f"Online translation is not available ({e}). Switching to offline translation (NLLB).")
            progress(0.0)
            translated = _nllb_translate(todo_raw, source, target, terms, log, progress, cancel)
            used_nllb = True
    else:
        translated = _nllb_translate(todo_raw, source, target, terms, log, progress, cancel, model)

    by_group = dict.fromkeys(range(len(groups)), "")
    for k, t in zip(todo, translated):
        by_group[k] = terms.finish(t)

    # NLLB sometimes leaves out half of a long sentence. Such groups are translated
    # again one cue at a time (each cue then simply gets its own translation).
    per_cue: dict[int, str] = {}
    if used_nllb:
        dropped = [todo[k] for k in _dropped_content(todo_texts, translated) if len(groups[todo[k]]) > 1]
        if dropped:
            _check_cancel(cancel)
            log(f"Translating {len(dropped)} long sentence(s) again, one subtitle at a time "
                "(part of the translation was missing).")
            cues = [i for k in dropped for i in groups[k]]
            again = _nllb_translate([" ".join(texts[i].split()) for i in cues],
                                    source, target, terms, log, lambda p: None, cancel, model)
            per_cue = {i: terms.finish(t) for i, t in zip(cues, again)}

    if return_groups:
        out: list[tuple[list[int], str]] = []
        for k, g in enumerate(groups):
            if all(per_cue.get(i) for i in g):     # re-translated cue by cue: one group per cue
                out += [([i], per_cue[i]) for i in g]
            elif by_group[k] or raw[k]:
                out.append((list(g), by_group[k] or raw[k]))   # untranslated: keep the source
        progress(1.0)
        return out

    no_spaces = target in _NO_SPACE_LANGS
    result = list(texts)
    for k, g in enumerate(groups):
        if not by_group[k]:
            continue
        pieces = _split_like(by_group[k], [len(texts[i]) for i in g], no_spaces)
        for i, p in zip(g, pieces):
            result[i] = per_cue.get(i) or p or texts[i]
    progress(1.0)
    return result
