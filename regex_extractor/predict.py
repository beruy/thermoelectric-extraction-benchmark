"""
Regex adapter for the benchmark contract (evaluation/schema.py).

Runs the frozen M0 rules (extractor.RegexExtractor, unchanged) on the method
input file and writes the common output format. Only the paragraph `text` is
used for extraction.

Usage (from the project root):
    python -m regex_extractor.predict --split dev
    python -m regex_extractor.predict --split test     # once, after all methods are frozen

Writes results/regex/<run_id>/: predictions.jsonl, paragraph_status.jsonl, run.json.
An existing run folder is never overwritten.

M0 note: the rules were developed on the full corpus before the dev/test split
(PROTOCOL.md §3, "corpus-informed baseline"); test scores are not scores on
unseen data.
"""

import argparse
import hashlib
import json
import platform
import time
from datetime import datetime, timezone
from pathlib import Path

from evaluation.schema import ALL_PROPERTIES, PREDICTION_FIELDS, validate_prediction

from .extractor import RegexExtractor

PKG = Path(__file__).resolve().parent
FROZEN_MANIFEST = PKG.parent / "evaluation" / "manifests" / "regex_frozen_2026-10-13.json"
KAPPA_MAP = {"lattice": "lattice", "electronic": "electronic", "bipolar": "bipolar",
             "total": "total", "total_or_unspecified": "unspecified"}


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_version():
    files = sorted(p for p in PKG.glob("*.py"))
    h = hashlib.sha256()
    for p in files:
        h.update(p.name.encode() + b"\0" + p.read_bytes())
    rules = sha256_file(PKG / "extractor.py")
    frozen = None
    if FROZEN_MANIFEST.exists():
        m = json.loads(FROZEN_MANIFEST.read_text(encoding="utf-8"))
        frozen = m["code"].get("regex_extractor/extractor.py")
    return {"package_sha256": h.hexdigest(), "rules_file_sha256": rules,
            "rules_match_frozen_manifest": (rules == frozen) if frozen else None}


def to_prediction(sample_id, c):
    """Map one regex Candidate (dict) to the contract record."""
    flags = list(c.get("flags") or [])
    rec = {f: None for f in PREDICTION_FIELDS}
    rec.update(sample_id=sample_id, property=c["property"], material=c.get("material"),
               T_K=c.get("T_K"), flags=flags, evidence=c.get("sentence"))
    qual = c.get("qualifier")
    if c["property"] == "doping":
        if qual == "carrier_concentration":
            rec["carrier_conc_cm3"] = c.get("value")
            rec["doping_text"] = c.get("value_text")
        else:
            rec["doping_text"] = " ".join(x for x in (c.get("value_text"), c.get("dopant")) if x) or None
    else:
        rec["value"] = c.get("value")
        rec["value_max"] = c.get("value_max")
        if c["property"] == "kappa":
            rec["kappa_type"] = KAPPA_MAP.get(qual)
        elif qual in ("max", "min", "avg"):
            rec["qualifier"] = qual
        if rec["value_max"] is not None:
            rec["qualifier"] = "range"
    if "computational_context" in flags:
        rec["context"] = "computational"
    # 'citation_in_sentence' only says a citation is nearby; origin stays unknown.
    return rec


def run(split, data_dir, out_root, run_id=None):
    inp = Path(data_dir) / split / "inputs.jsonl"
    run_id = run_id or f"{split}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    out = Path(out_root) / "regex" / run_id
    if out.exists():
        raise SystemExit(f"{out} exists; runs are never overwritten")
    out.mkdir(parents=True)

    started = datetime.now(timezone.utc)
    t0 = time.time()
    extractor = RegexExtractor()
    n_ok = n_failed = n_preds = n_invalid = 0
    with open(inp, encoding="utf-8") as fin, \
         open(out / "predictions.jsonl", "w", encoding="utf-8") as fp, \
         open(out / "paragraph_status.jsonl", "w", encoding="utf-8") as fs:
        for line in fin:
            if not line.strip():
                continue
            row = json.loads(line)
            sid = row["sample_id"]
            try:
                cands = extractor.extract(row["text"])
                preds = [to_prediction(sid, c.to_dict()) for c in cands]
            except Exception as e:  # recorded as a failed paragraph, not as "no records"
                fs.write(json.dumps({"sample_id": sid, "status": "error", "n_predictions": 0,
                                     "error": repr(e)}) + "\n")
                n_failed += 1
                continue
            for p in preds:
                if validate_prediction(p):
                    n_invalid += 1
                fp.write(json.dumps(p, ensure_ascii=False) + "\n")
            fs.write(json.dumps({"sample_id": sid, "status": "ok", "n_predictions": len(preds),
                                 "error": None}) + "\n")
            n_ok += 1
            n_preds += len(preds)

    meta = {
        "method_id": "M0", "method_name": "Regex baseline (regex_extractor)",
        "run_id": run_id, "split": split,
        "code_version": code_version(),
        "config": {"temp_window": extractor.temp_window},
        "model_id": None, "model_params": None,
        "input_file": str(inp), "input_sha256": sha256_file(inp),
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "wall_seconds": round(time.time() - t0, 3),
        "n_paragraphs": n_ok + n_failed, "n_ok": n_ok, "n_failed": n_failed,
        "n_predictions": n_preds, "n_invalid_predictions": n_invalid,
        "n_model_calls": 0, "input_tokens": None, "output_tokens": None,
        "cost_usd": 0.0, "price_table": None,
        "hardware": {"python": platform.python_version(), "machine": platform.machine(),
                     "system": platform.system()},
        "capabilities": ALL_PROPERTIES,
        "development_note": "corpus-informed baseline: rules developed on the full corpus "
                            "before the dev/test split (PROTOCOL.md §3)",
    }
    (out / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("run_id", "n_paragraphs", "n_failed",
                                           "n_predictions", "n_invalid_predictions",
                                           "wall_seconds")}, indent=2))
    print(f"-> {out}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run M0 (regex) on the benchmark input")
    ap.add_argument("--split", required=True, choices=["dev", "test"])
    ap.add_argument("--data", default="evaluation/data")
    ap.add_argument("--out", default="results")
    ap.add_argument("--run-id")
    args = ap.parse_args(argv)
    run(args.split, args.data, args.out, args.run_id)


if __name__ == "__main__":
    main()
