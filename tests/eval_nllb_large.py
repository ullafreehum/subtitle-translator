r"""Side-by-side quality and speed check: NLLB 1.3B ("nllb") vs NLLB 3.3B ("nllb_large").

    .venv\Scripts\python.exe tests\eval_nllb_large.py --data <folder> [--out report.txt] [--cpu]

<folder> holds sentence lists (sentences*.py with EN and TR lists; EN is translated
en->tr, TR tr->en) and optionally eval\*.cues.json (lists of {start, end, text};
"tr_*" files are Turkish speech, others English), translated with return_groups=True.
Uses the shipped glossary.example.txt. Needs models\nllb-200-3.3B (download_nllb_large()).
Writes a text report and a .json file with every translation next to it.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.stdout.reconfigure(encoding="utf-8")

import glossary  # noqa: E402
import translation  # noqa: E402

MODELS = ("nllb", "nllb_large")


def load_sets(data: Path) -> list[dict]:
    """[{"name", "source", "target", "texts", "cues"}] from the data folder."""
    sets = []
    for path in sorted(data.glob("sentences*.py")):
        spec = importlib.util.spec_from_file_location(path.stem, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        for var, src, tgt in (("EN", "en", "tr"), ("TR", "tr", "en")):
            if getattr(mod, var, None):
                sets.append({"name": f"{path.stem}.{var}", "source": src, "target": tgt,
                             "texts": list(getattr(mod, var)), "cues": False})
    for path in sorted((data / "eval").glob("*.final3.cues.json")):
        cues = json.loads(path.read_text(encoding="utf-8"))
        src = "tr" if path.name.startswith("tr_") else "en"
        sets.append({"name": path.name, "source": src, "target": "en" if src == "tr" else "tr",
                     "texts": [c["text"].replace("\n", " ") for c in cues], "cues": True})
    return sets


def run_model(model: str, sets: list[dict], gloss, log) -> dict:
    """Translate every set with one model; returns {"device", "load_s", "sets": {name: {...}}}."""
    translation.free_gpu_models()   # the large model fits on a 4 GB card only alone
    t0 = time.time()
    translation._load_nllb(log, model)
    load_s = time.time() - t0
    translation.translate_texts(["Warm up."], "en", "tr", model, None, lambda m: None)
    result = {"device": translation._nllb[model]["device"], "load_s": load_s, "sets": {}}
    for s in sets:
        t0 = time.time()
        if s["cues"]:   # whole sentence groups, as the re-timing engine uses them
            out = translation.translate_texts(s["texts"], s["source"], s["target"], model, gloss,
                                              lambda m: None, return_groups=True)
            # A group translated again cue by cue comes back as one-cue groups, so the
            # two models can split differently: join the pieces per sentence group.
            pieces = {i: t for idx, t in out for i in idx[:1]}
            items = [(" ".join(s["texts"][i] for i in g), " ".join(pieces[i] for i in g if i in pieces))
                     for g in translation._sentence_groups(s["texts"])]
        else:
            out = translation.translate_texts(s["texts"], s["source"], s["target"], model, gloss,
                                              lambda m: None)
            items = list(zip(s["texts"], out))
        secs = time.time() - t0
        result["sets"][s["name"]] = {"items": items, "seconds": secs}
        log(f"  {model}: {s['name']}: {len(items)} items in {secs:.1f}s")
    # Device may have changed (GPU failure -> CPU) during the run.
    result["device_end"] = translation._nllb.get(model, {}).get("device", result["device"])
    translation.free_gpu_models()
    return result


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True, type=Path)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--cpu", action="store_true", help="run both models on the CPU")
    args = ap.parse_args()
    if not translation._model_complete(translation.NLLB_LARGE_DIR):
        sys.exit(f"The large model is not installed in {translation.NLLB_LARGE_DIR}.")
    if args.cpu:
        translation._nllb_cpu_only = True
    out = args.out or args.data / "nllb_large_report.txt"
    gloss = glossary.load_glossary(glossary.EXAMPLE_PATH)
    sets = load_sets(args.data)
    log = lambda m: print(m, flush=True)  # noqa: E731
    results = {m: run_model(m, sets, gloss, log) for m in MODELS}

    lines = ["NLLB 1.3B (nllb) vs NLLB 3.3B (nllb_large), glossary.example.txt", ""]
    for m, r in results.items():
        total = sum(v["seconds"] for v in r["sets"].values())
        n = sum(len(v["items"]) for v in r["sets"].values())
        lines.append(f"{m}: device {r['device']} (end: {r['device_end']}), load {r['load_s']:.1f}s, "
                     f"{n} items in {total:.1f}s ({total / max(1, n):.2f} s/item)")
    lines.append("")
    for s in sets:
        a = results["nllb"]["sets"][s["name"]]
        b = results["nllb_large"]["sets"][s["name"]]
        same = sum(x[1] == y[1] for x, y in zip(a["items"], b["items"]))
        lines += [f"=== {s['name']} ({s['source']} -> {s['target']}): {len(a['items'])} items, "
                  f"{same} identical; 1.3B {a['seconds']:.1f}s, 3.3B {b['seconds']:.1f}s", ""]
        for k, (x, y) in enumerate(zip(a["items"], b["items"]), 1):
            mark = "=" if x[1] == y[1] else "*"
            lines += [f"{mark} {k}. SRC: {x[0]}", f"     1.3B: {x[1]}", f"     3.3B: {y[1]}", ""]
    out.write_text("\n".join(lines), encoding="utf-8")
    out.with_suffix(".json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n".join(lines[:4]))
    print(f"Report: {out}")


if __name__ == "__main__":
    main()
