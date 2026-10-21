"""
Method M2: PolymerNER (MaterialsBERT encoder) + the published rule-based record
linking of Shetty et al. (npj Comput. Mater. 9, 52, 2023), applied to the
benchmark paragraphs. No LLM step, no retraining.

Pipeline per paragraph:
  1. normalise_text: unit exponents to the authors' "^{-1}" notation   [ours]
  2. PolymerNER token classification, sentence chunks of <= 512 tokens  [model; chunking ours]
  3. utils.ner_feed + record_extractor.RelationExtraction (vendored, polymer_filter=False)
                                                                          [authors' code]
  4. map_record: property-name dictionary, unit conversion, temperature  [ours]

Needs its own environment (Python 3.8, chemdataextractor 1.3.0, torch,
transformers 4.30, spaCy + en_core_web_sm); see materialsbert_extractor/README.md.

    python -m materialsbert_extractor.predict --selftest
    python -m materialsbert_extractor.predict --split dev

Writes results/bert/<run_id>/ (never overwritten): predictions.jsonl,
paragraph_status.jsonl, run.json, raw/records.jsonl (NER entities and every
linked record with the reason it was kept or dropped).

The legacy files of this folder (cli.py, extractor.py, schema.py, ...) are a
pre-benchmark NanoSynthra module and are not used here.
"""

import argparse
import hashlib
import json
import os
import platform
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from evaluation.schema import PREDICTION_FIELDS, validate_prediction
from materialsbert_extractor.units import to_canonical

PKG = Path(__file__).resolve().parent
VENDOR = PKG / "vendor" / "polymer_information_extraction"
METADATA = PKG / "property_metadata.json"
MODEL_NAME = "pranav-s/PolymerNER"
MAX_TOKENS = 510            # 512 minus [CLS] and [SEP]
CAPABILITIES = ["ZT", "S_uVK", "kappa", "sigma", "PF", "doping"]


# ---------------------------------------------------------------------------
# 1. Text normalisation (ours): exponents in units -> "^{-1}" notation, which
#    the authors' number parser expects (otherwise "-1" in "m-1" is read as a number)
# ---------------------------------------------------------------------------
_UNIT_ATOM = r"(?:[μµu]?(?:cm|mm|m|K|V|W|S|Ω|g|s|mol|A|Pa|J)|°C)"
_SUP = str.maketrans("⁻⁰¹²³⁴⁵⁶⁷⁸⁹", "-0123456789")


def normalise_text(text):
    t = text.replace("−", "-").replace("–", "-").replace("µ", "μ")
    # superscript exponents: "cm⁻³" -> "cm^{-3}"
    t = re.sub(r"[⁻⁰¹²³⁴⁵⁶⁷⁸⁹]+", lambda m: "^{" + m.group(0).translate(_SUP) + "}", t)
    # "1.3 × 10-2", "2 x 10^20" -> "1.3x10^{-2}", "2x10^{20}" (the form the authors' RE_NUMBER reads)
    t = re.sub(r"(\d)\s*[×x]\s*10\s*\^?\s*\{?(-?\d+)\}?(?!\d)", lambda m: m.group(1) + "x10^{" + m.group(2) + "}", t)
    # unit exponents: "W m-1 K-1", "Wm-1K-1", "cm-3", "K^-2" -> "^{-1}" (one-digit exponents only,
    # so "300 K-1000 K" or "Bi2Te3-x" are left alone)
    t = re.sub(r"(" + _UNIT_ATOM + r")\s?\^?\s?(-[1-9])(?!\d|\.\d)", r"\1^{\2}", t)
    # positive exponents of K after a length unit: "W/m. K^2", "W/mK2", "μW/cm K2" -> "K^{2}"
    # (the authors' number parser otherwise takes the "2" as a value)
    t = re.sub(r"((?:/|\b)(?:c?m)\.?\s?K)\s?\^?\s?([2-9])(?!\d|\.\d|\^)", r"\1^{\2}", t)
    t = re.sub(r"\^\{\^\{", "^{", t)
    return t


# ---------------------------------------------------------------------------
# 4. Property-name dictionary and record mapping (ours)
# ---------------------------------------------------------------------------
_SYMBOLS = {
    "zt": "ZT", "zt_max": "ZT", "ztmax": "ZT", "zt max": "ZT",
    "s": "S_uVK", "α": "S_uVK",
    "κ": "kappa", "κl": "kappa", "κ_l": "kappa", "κe": "kappa", "κ_e": "kappa", "κlat": "kappa",
    "κ_lat": "kappa", "k": "kappa", "kl": "kappa", "k_l": "kappa", "λ": "kappa",
    "σ": "sigma", "ρ": "sigma", "pf": "PF",
}


def property_of(name):
    """(property, is_resistivity) for a PROP_NAME entity, or (None, False)."""
    n = (name or "").lower().strip()
    if not n:
        return None, False
    if "figure of merit" in n or re.search(r"(^|[\s(])zt", n):
        return "ZT", False
    if "seebeck" in n or "thermopower" in n or "thermoelectric power" in n:
        return "S_uVK", False
    if "power factor" in n:
        return "PF", False
    if "thermal conductiv" in n:
        return "kappa", False
    if "resistiv" in n:
        return "sigma", True
    if "conductiv" in n and "thermal" not in n and "ionic" not in n:
        return "sigma", False
    if re.search(r"(carrier|hole|electron)s? (concentration|density)", n):
        return "doping", False
    if n in _SYMBOLS:
        return _SYMBOLS[n], n == "ρ"
    return None, False


def kappa_type(name):
    n = (name or "").lower()
    if "lattice" in n or re.search(r"κ_?l|k_?l\b", n):
        return "lattice"
    if "electronic" in n or re.search(r"κ_?e", n):
        return "electronic"
    if "bipolar" in n:
        return "bipolar"
    return "total"


RE_NUMBER = r"[+-]?\d+[.]?\d*(?:x10\^{[-]?\d*})?"   # authors' RE_NUMBER without the ± part


def _num(s):
    if "x10^{" in s:
        m, e = s.split("x10^{")
        return float(m) * 10 ** float(e.rstrip("}"))
    return float(s)


def celsius_to_kelvin(cond):
    m = re.match(r"\s*(-?\d+(?:\.\d+)?)\s*°\s*C", cond or "")
    return round(float(m.group(1)) + 273.15, 2) if m else None


def map_record(sample_id, rec, all_materials):
    """One linked record of the authors' pipeline -> (prediction, None) or (None, reason)."""
    pr = rec.get("property_record") or {}
    names = [pr.get("entity_name")] + list(pr.get("coreferents") or [])
    prop, resistivity = None, False
    for nm in names:
        prop, resistivity = property_of(nm)
        if prop:
            break
    if not prop:
        return None, f"property name not in dictionary: {pr.get('entity_name')!r}"
    value = pr.get("property_numeric_value")
    if value in ("", None):
        return None, "no numeric value"
    unit = pr.get("property_unit") or ""
    descriptor = pr.get("property_value_descriptor") or ""
    raw_value = pr.get("property_value") or ""
    # ranges ("300 to 500", "1.2-1.5"): authors average the numbers; we keep the bounds
    low = high = None
    nums = re.findall(RE_NUMBER, re.sub(r"(\d)-(\d)", r"\1 - \2", raw_value.replace(" x ", "x")))
    if len(nums) >= 2 and ("to" in descriptor or "-" in descriptor) and "±" not in raw_value:
        vals = sorted(_num(x) for x in nums[:2])
        low, high = vals
    if low is not None:
        lo, why = to_canonical(prop, low, unit, resistivity)
        hi, why2 = to_canonical(prop, high, unit, resistivity)
        if lo is None or hi is None:
            return None, why or why2
        lo, hi = sorted((lo, hi))
        v, vmax, qual = lo, hi, "range"
    else:
        v, why = to_canonical(prop, float(value), unit, resistivity)
        if v is None:
            return None, why
        vmax, qual = None, None
    mats = rec.get("material_name") or []
    names_m = sorted({m.get("entity_name") for m in mats if isinstance(m, dict) and m.get("entity_name")})
    flags = []
    if len(names_m) == 1:
        material = names_m[0]
    else:
        material = None
        if len(names_m) > 1:
            flags.append("ambiguous_attribution")
    p = {f: None for f in PREDICTION_FIELDS}
    p.update({"sample_id": sample_id, "property": prop, "material": material,
              "value": None if prop == "doping" else v, "value_max": None if prop == "doping" else vmax,
              "qualifier": qual if prop != "doping" else None,
              "T_K": celsius_to_kelvin(pr.get("temperature_condition")),
              "kappa_type": kappa_type(pr.get("entity_name")) if prop == "kappa" else None,
              "carrier_conc_cm3": v if prop == "doping" else None,
              "flags": flags, "evidence": raw_value or None})
    if "<" in descriptor or ">" in descriptor:
        p["flags"].append("bound")
    return p, None


# ---------------------------------------------------------------------------
# 2-3. NER and the authors' record linking
# ---------------------------------------------------------------------------
class Pipeline:
    def __init__(self, revision=None, device=-1):
        os.environ["PROPERTY_METADATA_FILE"] = str(METADATA)
        if str(VENDOR) not in sys.path:
            sys.path.insert(0, str(VENDOR))
        import record_extractor
        import utils as vendor_utils
        from huggingface_hub import model_info
        from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline
        info = model_info(MODEL_NAME, revision=revision)
        self.revision = info.sha
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME, revision=self.revision, model_max_length=512)
        model = AutoModelForTokenClassification.from_pretrained(MODEL_NAME, revision=self.revision)
        self.ner = pipeline("ner", model=model, tokenizer=self.tokenizer, aggregation_strategy="simple",
                            device=device)
        self.record_extractor, self.vendor_utils = record_extractor, vendor_utils
        self.stats = {"chunks": 0, "overlong_sentences": 0, "chunks_over_limit": 0}

    def ntok(self, text):
        return len(self.tokenizer.tokenize(text))

    def chunks(self, text):
        """Consecutive pieces of at most MAX_TOKENS word pieces, as (start, end).

        Sentences are grouped greedily; a sentence that alone exceeds the limit is
        cut at whitespace into windows that fit (the pipeline would otherwise
        truncate it silently). Counts are kept in self.stats."""
        bounds = [m.end() for m in re.finditer(r"(?<=[.!?])\s+(?=[A-Z(\[])", text)]
        pieces = []
        for s, e in zip([0] + bounds, bounds + [len(text)]):
            if self.ntok(text[s:e]) <= MAX_TOKENS:
                pieces.append((s, e))
                continue
            self.stats["overlong_sentences"] += 1
            words = [m.start() for m in re.finditer(r"\S+", text[s:e])]
            cur = s
            for k in range(1, len(words) + 1):
                end = s + words[k] if k < len(words) else e
                if self.ntok(text[cur:end]) > MAX_TOKENS and end > cur:
                    prev = s + words[k - 1]
                    if prev > cur:
                        pieces.append((cur, prev))
                        cur = prev
            pieces.append((cur, e))
        out = []
        for s, e in pieces:
            if out and self.ntok(text[out[-1][0]:e]) <= MAX_TOKENS:
                out[-1] = (out[-1][0], e)
            else:
                out.append((s, e))
        self.stats["chunks"] += len(out)
        self.stats["chunks_over_limit"] += sum(self.ntok(text[s:e]) > MAX_TOKENS for s, e in out)
        return out

    def entities(self, text):
        ents = []
        for s, e in self.chunks(text):
            for ent in self.ner(text[s:e]):
                ents.append({"entity_group": ent["entity_group"], "word": ent["word"],
                             "score": float(ent["score"]), "start": ent["start"] + s, "end": ent["end"] + s})
        return ents

    def link(self, text, ents):
        if not ents:
            return []
        spans = self.vendor_utils.ner_feed(ents, text)
        rel = self.record_extractor.RelationExtraction(text=text, spans=spans, normalization_dataset={},
                                                       polymer_filter=False, verbose=False)
        out, _ = rel.process_document()
        return (out or {}).get("material_records", []) if out else []


def extract(pipe, sample_id, text):
    norm = normalise_text(text)
    ents = pipe.entities(norm)
    recs = pipe.link(norm, ents)
    preds, log = [], []
    for r in recs:
        p, reason = map_record(sample_id, r, None)
        log.append({"record": r, "kept": p is not None, "drop_reason": reason})
        if p:
            preds.append(p)
    # identical records collapse (the scorer also collapses duplicates)
    seen, unique = set(), []
    for p in preds:
        k = json.dumps(p, sort_keys=True)
        if k not in seen:
            seen.add(k)
            unique.append(p)
    return unique, {"normalised_text": norm, "entities": ents, "records": log}


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tree_sha256(folder):
    h = hashlib.sha256()
    for f in sorted(Path(folder).rglob("*.py")):
        h.update(str(f.relative_to(folder)).encode())
        h.update(f.read_bytes())
    return h.hexdigest()


def run(split, data_dir="evaluation/data", out_root="results", run_id=None, limit=None, revision=None,
        pipeline_commit=None):
    inp = Path(data_dir) / split / "inputs.jsonl"
    rows = [json.loads(l) for l in open(inp, encoding="utf-8") if l.strip()]
    if limit:
        rows = rows[:limit]
    run_id = run_id or f"{split}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    out = Path(out_root) / "bert" / run_id
    if out.exists():
        raise SystemExit(f"{out} exists; runs are never overwritten")
    pipe = Pipeline(revision)
    (out / "raw").mkdir(parents=True)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.time()
    n_ok = n_failed = n_preds = n_invalid = n_linked = 0
    dropped = {}
    with open(out / "predictions.jsonl", "w", encoding="utf-8") as fp, \
         open(out / "paragraph_status.jsonl", "w", encoding="utf-8") as fs, \
         open(out / "raw" / "records.jsonl", "w", encoding="utf-8") as fr:
        for i, row in enumerate(rows, start=1):
            sid = row["sample_id"]
            try:
                preds, log = extract(pipe, sid, row["text"])
            except Exception as e:  # recorded per paragraph; the run continues
                fs.write(json.dumps({"sample_id": sid, "status": "error", "n_predictions": 0,
                                     "error": repr(e)[:500]}) + "\n")
                n_failed += 1
                continue
            fr.write(json.dumps({"sample_id": sid, **log}, ensure_ascii=False, default=str) + "\n")
            for r in log["records"]:
                n_linked += 1
                if not r["kept"]:
                    key = r["drop_reason"].split(":")[0]
                    dropped[key] = dropped.get(key, 0) + 1
            for p in preds:
                n_invalid += bool(validate_prediction(p))
                fp.write(json.dumps(p, ensure_ascii=False) + "\n")
            fs.write(json.dumps({"sample_id": sid, "status": "ok", "n_predictions": len(preds),
                                 "error": None}) + "\n")
            n_ok += 1
            n_preds += len(preds)
            if i % 10 == 0:
                print(f"  {i}/{len(rows)} paragraphs, {n_preds} predictions", flush=True)
    import torch
    import transformers
    meta = {
        "method_id": "M2", "method_name": "PolymerNER (MaterialsBERT) + published rule-based linking",
        "run_id": run_id, "split": split,
        "code_version": {"predict_sha256": sha256_file(__file__),
                         "units_sha256": sha256_file(PKG / "units.py"),
                         "property_metadata_sha256": sha256_file(METADATA),
                         "vendor_sha256": tree_sha256(VENDOR),
                         "pipeline_commit": pipeline_commit or "d08f2d301fb74c680d8df9b3993d496b069fc6e9"},
        "config": {"max_tokens_per_chunk": MAX_TOKENS, "polymer_filter": False, "limit": limit},
        "model_id": MODEL_NAME, "model_params": {"revision": pipe.revision, "aggregation_strategy": "simple",
                                                  "torch": torch.__version__,
                                                  "transformers": transformers.__version__},
        "input_file": str(Path("evaluation/data") / split / "inputs.jsonl"), "input_sha256": sha256_file(inp),
        "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "wall_seconds": round(time.time() - t0, 1),
        "n_paragraphs": n_ok + n_failed, "n_ok": n_ok, "n_failed": n_failed,
        "n_predictions": n_preds, "n_invalid_predictions": n_invalid,
        "n_linked_records": n_linked, "dropped_by_mapping": dropped,
        "chunking": pipe.stats,
        "n_model_calls": 0, "input_tokens": None, "output_tokens": None, "cost_usd": 0.0, "price_table": None,
        "hardware": {"python": platform.python_version(), "machine": platform.machine(),
                     "system": platform.system()},
        "capabilities": CAPABILITIES,
    }
    (out / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("run_id", "n_paragraphs", "n_failed", "n_predictions",
                                           "n_invalid_predictions", "n_linked_records", "dropped_by_mapping", "chunking",
                                           "wall_seconds")}, indent=2, ensure_ascii=False))
    print(f"-> {out}")
    return out


SELFTEST = [
    "The Seebeck coefficient of Bi2Te3 is 200 μV K-1 at room temperature.",
    "SnSe shows a low thermal conductivity of 0.56 W m-1 K-1 and a high ZT of 2.6.",
    "The electrical conductivity of PbTe reaches 1000 S cm-1, and its power factor is 25 μW cm-1 K-2.",
    "The resistivity of Cu2Se is 10 μΩ m at 50 °C.",
]


def selftest(revision=None):
    pipe = Pipeline(revision)
    print("model revision:", pipe.revision)
    for t in SELFTEST:
        preds, log = extract(pipe, "T", t)
        print(t)
        print("   normalised:", log["normalised_text"])
        print("   entities:  ", [(e["entity_group"], e["word"]) for e in log["entities"]])
        for r in log["records"]:
            pr = r["record"].get("property_record", {})
            print("   linked:    ", pr.get("entity_name"), "|", pr.get("property_value"), "|",
                  pr.get("property_unit"), "|", [m.get("entity_name") for m in r["record"].get("material_name", [])],
                  "|", "kept" if r["kept"] else r["drop_reason"])
        for p in preds:
            print("   PREDICTION:", p["property"], p["value"], p["value_max"], p["material"], p["T_K"])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run M2 (PolymerNER + published linking)")
    ap.add_argument("--split", choices=["dev", "test"])
    ap.add_argument("--data", default="evaluation/data")
    ap.add_argument("--out", default="results")
    ap.add_argument("--run-id")
    ap.add_argument("--revision", help="model revision (commit sha); default: current")
    ap.add_argument("--pipeline-commit")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        selftest(args.revision)
        return
    if not args.split:
        ap.error("--split is required unless --selftest")
    run(args.split, args.data, args.out, args.run_id, args.limit, args.revision, args.pipeline_commit)


if __name__ == "__main__":
    main()
