r"""Quick checks for glossary.py and translation.py (plain python, no pytest).

    .venv\Scripts\python.exe tests\test_translation.py            # glossary + NLLB
    .venv\Scripts\python.exe tests\test_translation.py --online   # also Google/MyMemory
    .venv\Scripts\python.exe tests\test_translation.py --cpu      # force NLLB on CPU
"""

from __future__ import annotations

import re
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import glossary  # noqa: E402
import translation  # noqa: E402
from translation import Cancelled, translate_texts  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "sample_segments.json"
GLOSSARY = glossary.load_glossary(glossary.EXAMPLE_PATH)


def fixture_texts(path: Path) -> list[str]:
    """Cue texts built from real Whisper output (a made-up training interview, see tests/sample_media.py)."""
    import json
    import subtitles
    cues = subtitles.build_cues(json.loads(path.read_text(encoding="utf-8")))
    return [c.text.replace("\n", " ") for c in cues]


def check(cond: bool, msg: str) -> None:
    print(("  ok    " if cond else "  FAIL  ") + msg)
    if not cond:
        check.failed += 1


check.failed = 0


def test_glossary() -> None:
    print("\n== glossary")
    g = GLOSSARY
    check("DİLGEM" in g.keep_terms and "DIR Floortime" in g.keep_terms, "keep terms loaded")
    check(g.translations("en", "tr").get("trainees") == "katılımcılar", "[en>tr] trainees (DİLGEM usage)")
    check(g.translations("tr", "en").get("DEHB") == "ADHD", "[tr>en] DEHB")
    check(g.translations("de", "tr") == {}, "unknown pair is empty")
    p = g.whisper_prompt()
    print("  whisper prompt:", p)
    check(0 < len(p) <= glossary.WHISPER_PROMPT_MAX and p.startswith("DİLGEM"), "whisper prompt short")
    check(bool(g.hints) and p.index(g.hints[1]) < p.index("JASPER"), "hints come first in the prompt")
    fixed = g.fix_terms("Dilgem'in eğitimi, Jasper'ı ve dir floortime; PECS ve ABA.")
    check(fixed == "DİLGEM'in eğitimi, JASPER'ı ve DIR Floortime; PECS ve ABA.", f"fix_terms: {fixed}")
    # Short abbreviations are case-sensitive: everyday words stay untouched.
    kept = g.fix_terms("Bir aba giydi; two cars; pecs. She calms the child.")
    check(kept == "Bir aba giydi; two cars; pecs. She calms the child.", f"abbreviations case-sensitive: {kept}")
    check(g.fix_terms("Dilgem ve Jasper") == "DİLGEM ve JASPER", "capitalised names still fixed")
    corr = glossary.parse_glossary("[tr>tr]\nterapotik = terapötik\n")
    check(corr.fix_terms("terapotik ilişki", "tr") == "terapötik ilişki", "[tr>tr] correction")
    check(corr.fix_terms("terapotik", "en") == "terapotik", "correction only for its language")
    m = glossary.TermMap(g.translations("en", "tr"))
    check(m.sub("The trainee met the Trainees.") == "The katılımcı met the katılımcılar.", "whole-word, longest first")
    sm = glossary.TermMap({"filial terapi": "filial therapy"}, suffixes=True)
    check(sm.sub("Filial terapide") == "filial therapy'de", f"suffix match: {sm.sub('Filial terapide')}")
    c = g.fix_terms("Filaterapide ve çocuk merkezi oyun terapisinde", "tr")
    check(c == "filial terapide ve çocuk merkezli oyun terapisinde", f"corrections keep endings: {c}")
    check(glossary.load_glossary(str(ROOT / "no-such-file.txt")).keep_terms == [], "missing file -> empty")


def test_helpers() -> None:
    print("\n== helpers")
    s = translation._split_sentences("Dr. Smith came. Yes, absolutely. it was fine? Good")
    check(s == ["Dr. Smith came.", "Yes, absolutely.", "it was fine?", "Good"], f"split sentences: {s}")
    c = translation._clean_output("Thank you.", "- Teşekkür ederim. - Evet.")
    check(c == "Teşekkür ederim.", f"dialogue cleanup: {c}")
    c = translation._clean_output("Thank you.", "Teşekkür ederim. Teşekkürler.")
    check(c == "Teşekkür ederim.", f"repeat cleanup: {c}")
    terms = translation._Terms(GLOSSARY, "en", "tr")
    # Forced terms go in as written; the capital at a sentence start is restored on the output.
    check(terms.prepare("Trainees and trainees.") == "katılımcılar and katılımcılar.", "prepare: terms as written")
    check(translation._Terms(GLOSSARY, "en", "tr").prepare("OTs and SLPs") ==
          "ergoterapistler and dil ve konuşma terapistleri", "abbreviations translated, no stray capitals")
    f = terms.finish("Katılımcılar'ın Jasper'ı ve Dilgem")
    check(f == "Katılımcıların JASPER'ı ve DİLGEM", f"finish: {f}")
    prot, values = terms.protect("the katılımcılar practice JASPER with JASPER")
    r = terms.finish(terms.restore("ZX1'le ZX2'yi ZX2", values))
    check(prot == "the ZX1 practice ZX2 with ZX2" and r == "katılımcılarla JASPER'yi JASPER", f"protect/restore: {prot} / {r}")
    for word, sfx, want in [("pekiştireç", "i", "pekiştireci"), ("öz düzenleme", "ü", "öz düzenlemeyi"),
                            ("iletişim çemberleri", "yi", "iletişim çemberlerini"),
                            ("hedef davranış", "den", "hedef davranıştan"), ("oyun odası", "ndaki", "oyun odasındaki"),
                            ("ketleyici kontrol", "u", "ketleyici kontrolü"), ("filial terapi", "yi", "filial terapiyi")]:
        got = translation._tr_suffix(word, sfx)
        check(got == want, f"Turkish suffix {word}+{sfx}: {got}")
    for word, sfx, want in [("postüral kontrol", "yü", "postüral kontrolü"),
                            ("tekerlekli sandalye", "yeye", "tekerlekli sandalyeye"),
                            ("davranış müdahale planı", "yı", "davranış müdahale planını")]:
        got = translation._tr_suffix(word, sfx)
        check(got == want, f"Turkish suffix {word}+{sfx}: {got}")
    f = terms.finish("Örneğin, panik bozukluk olan bir adam")
    check(f == "Örneğin, panik bozukluğu olan bir adam", f"bozukluk olan -> bozukluğu olan: {f}")
    parts = translation._split_like("bir iki üç dört beş altı", [10, 10, 10], False)
    check(len(parts) == 3, f"split_like: {parts}")
    # Regressions
    c = translation._clean_output("minus 5 degrees", "-5 derece")
    check(c == "-5 derece", f"minus sign kept: {c}")
    g = translation._sentence_groups(["", "Hello there.", "  ", "How", "are you?", ""])
    check(g == [[1], [3, 4]], f"empty cues belong to no group: {g}")
    z = translation._cjk_punctuation("大家早上好. 今天, 我们讨论3.5个问题?", "zh")
    check(z == "大家早上好。 今天， 我们讨论3.5个问题？", f"CJK punctuation: {z}")
    f = translation._fix_spacing("You have a duty to warn . It 's not , ok ?", "en")
    check(f == "You have a duty to warn. It's not, ok?", f"spaced punctuation: {f}")
    f = translation._fix_spacing("Oui ! Bien , merci .", "fr")
    check(f == "Oui ! Bien, merci.", f"French spacing kept: {f}")
    d = translation._dropped_content(["a" * 100, "b" * 100, "c" * 100, "d" * 100],
                                     ["x" * 105, "y" * 98, "z" * 30, "w" * 110])
    check(d == [2], f"dropped content detected: {d}")


def test_download_status() -> None:
    print("\n== model download messages")
    from huggingface_hub.utils import tqdm
    msgs: list[str] = []
    old = sys.stderr
    sys.stderr = None              # like the GUI started with pythonw.exe
    try:
        with translation.download_status("the test model", "about 1 GB", msgs.append, every=0.2):
            for _ in tqdm(range(3), desc="progress bar"):   # must not crash without a console
                time.sleep(0.2)
    finally:
        sys.stderr = old
    check(bool(msgs) and "still downloading the test model (about 1 GB)" in msgs[0],
          f"download is reported as still going: {msgs[:1]}")


def run(texts, source, target, name, translator="nllb"):
    t0 = time.time()
    out = translate_texts(texts, source, target, translator=translator, glossary=GLOSSARY,
                          log=lambda m: print("  [log]", m))
    print(f"  {name}: {len(texts)} cues in {time.time() - t0:.1f}s")
    check(len(out) == len(texts), "same number of outputs as inputs")
    return out


def test_en_tr(translator="nllb") -> None:
    print(f"\n== {translator}: en -> tr ({FIXTURE.name})")
    texts = fixture_texts(FIXTURE)
    out = run(texts, "en", "tr", "en->tr", translator)
    for a, b in zip(texts, out):
        print(f"  EN: {a}\n  TR: {b}")
    joined = " ".join(out)
    n_src = sum(len(re.findall(r"(?i)\btrainees?\b", t)) for t in texts)
    n_out = len(re.findall(r"(?i)\bkatılımcı", joined))
    check(n_out >= n_src, f"'trainee(s)' -> katılımcı: {n_out}/{n_src}")
    check("Dilgem" not in joined and "Jasper" not in joined, "no wrong casing of DİLGEM/JASPER")
    n_dilgem = sum(len(re.findall(r"(?i)\bd[iİı]lgem", t)) for t in texts)
    check(joined.count("DİLGEM") >= n_dilgem, f"DİLGEM kept: {joined.count('DİLGEM')}/{n_dilgem}")


def test_tr_en(translator="nllb") -> None:
    print(f"\n== {translator}: tr -> en")
    texts = ["Dilgem'in eğitimi çok iyiydi ve kursiyerler", "JASPER'ı çok sevdi. DİLGEM ile çalışmak güzeldi.",
             "DEHB'li çocuklarla oyun terapisi yaptık.", "Özel eğitim alanında dil ve konuşma terapisti olarak",
             "çalışıyorum. Otizm hakkında konuştuk."]
    out = run(texts, "tr", "en", "tr->en", translator)
    for a, b in zip(texts, out):
        print(f"  TR: {a}\n  EN: {b}")
    joined = " ".join(out)
    check("DİLGEM" in joined and "JASPER" in joined and "ADHD" in joined, "terms kept/forced")
    check(re.search(r"(?i)trainees", joined) is not None, "kursiyerler -> trainees")


def test_other_target() -> None:
    print("\n== nllb: en -> ar / de")
    texts = ["We practiced Jasper with the families", "and the trainees at Dilgem."]
    for tgt in ("ar", "de"):
        out = run(texts, "en", tgt, f"en->{tgt}")
        print("  ", out)
        check("JASPER" in " ".join(out) and "DİLGEM" in " ".join(out), f"{tgt}: keep terms present")


def test_languages() -> None:
    print("\n== nllb: every language of the app, empty and long cues")
    import engine
    from tokenizers import Tokenizer
    tok = Tokenizer.from_file(str(translation.NLLB_DIR / "tokenizer.json"))
    codes = {code: translation._FLORES.get(code) for code in engine.LANGUAGES.values()}
    bad = {c: f for c, f in codes.items() if not f or tok.token_to_id(f) is None}
    check(not bad, f"all {len(codes)} languages have a valid NLLB code: {bad or 'ok'}")
    out = translate_texts(["", "Thank you very much.", " ", ""], "en", "tr", log=lambda m: None)
    check(out[0] == "" and out[2] == " " and out[3] == "" and "teşekkür" in out[1].lower(), f"empty cues stay empty: {out}")
    old = translation._FLORES["tr"]
    translation._FLORES["tr"] = "tur_Latm"   # a typo must fail loudly, not give garbage
    try:
        translate_texts(["Hello."], "en", "tr", log=lambda m: None)
        check(False, "invalid FLORES code raises TranslationError")
    except translation.TranslationError as e:
        check("tur_Latm" in str(e), f"invalid FLORES code raises TranslationError: {e}")
    finally:
        translation._FLORES["tr"] = old


def test_cancel() -> None:
    print("\n== cancel")
    ev = threading.Event()
    ev.set()
    try:
        translate_texts(["Hello."], "en", "tr", cancel=ev, log=lambda m: None)
        check(False, "Cancelled raised")
    except Cancelled:
        check(True, "Cancelled raised")


if __name__ == "__main__":
    if "--cpu" in sys.argv:
        translation._nllb_cpu_only = True
    test_glossary()
    test_helpers()
    test_download_status()
    test_cancel()
    test_languages()
    test_en_tr()
    test_tr_en()
    test_other_target()
    if "--online" in sys.argv:
        test_en_tr("online")
        test_tr_en("online")
    print(f"\n{'ALL OK' if not check.failed else f'{check.failed} FAILED'}")
    sys.exit(1 if check.failed else 0)
