"""
Method M1: ChemDataExtractor thermoelectric parsers (Sierepeklis & Cole 2022).

Runs the published thermoelectric adaptation of ChemDataExtractor 2.0
(github.com/odysie/thermoelectricsdb, package ChemDataExtractor-TE 2.0.0-te,
function `te_parse`) on every benchmark paragraph, applies the authors' record
cleaning and unit normalisation (data_cleaning.ipynb), and maps the records to
the prediction contract (PROTOCOL.md §8). No LLM step.

Needs the authors' environment: Python 3.8, the unpacked ChemDataExtractor-TE
package on PYTHONPATH, its data files (`Package.download()`) and pandas < 2.
See chem_data_extractor/README.md for the Colab setup.

    python -m chem_data_extractor.predict --selftest
    python -m chem_data_extractor.predict --split dev --te-commit <thermoelectricsdb commit>

Writes results/cde/<run_id>/ (never overwritten): predictions.jsonl,
paragraph_status.jsonl, run.json and raw/te_records.jsonl (every record
te_parse returned, before cleaning, with the reason it was kept or dropped).

Kept as in the published pipeline: the parsers, the property models (ZT,
Seebeck, ThermCond, Conductivity, Conductivity2, Resistivity, PF), the rule that
a record needs a compound name and a temperature (inside te_parse), the cleaning
filters, prefix normalisation, sigma = 1/rho, room temperature = 295 K, and the
thermal-conductivity type tagging from the specifier.
Our mapping (documented, not part of the published pipeline): canonical units
of the contract, a value list of two or more numbers becomes a range
(value = min, value_max = max) instead of the authors' average, the first
compound name is the material, and no doping records (M1 has no doping model).

The legacy files of this folder (cli.py, extractor.py, schema.py) predate the
benchmark and are not used here.
"""

import argparse
import hashlib
import json
import platform
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from string import ascii_letters

from evaluation.schema import PREDICTION_FIELDS, validate_prediction

PKG = Path(__file__).resolve().parent

# te_parse model name -> contract property
MODEL_PROPERTY = {
    "ZT": "ZT", "Seebeck": "S_uVK", "ThermCond": "kappa",
    "Conductivity": "sigma", "Conductivity2": "sigma", "Resistivity": "sigma", "PF": "PF",
}
MODEL_ORDER = ["ZT", "Seebeck", "ThermCond", "Conductivity", "Conductivity2", "Resistivity", "PF"]
# Authors' normalised (SI) unit -> contract canonical unit
TO_CANONICAL = {
    "ZT": 1.0,           # dimensionless
    "S_uVK": 1e6,        # V K-1 -> uV K-1
    "kappa": 1.0,        # W m-1 K-1
    "sigma": 1.0,        # S m-1
    "PF": 1e4,           # W m-1 K-2 -> uW cm-1 K-2
}
CAPABILITIES = ["ZT", "S_uVK", "kappa", "sigma", "PF"]
ROOM_TEMPERATURE_K = 295.0   # authors' convention (data_cleaning.ipynb, make_temp_number_list)


# ---------------------------------------------------------------------------
# Collecting te_parse records without its pandas DataFrame
# ---------------------------------------------------------------------------
class RecordList(list):
    """Stands in for the DataFrame te_parse fills: add_record_to_database calls
    df.append(dict, ignore_index=True) and keeps the return value, so a list
    whose append returns itself collects the same dictionaries (pandas 2 has no
    DataFrame.append; this keeps the authors' code unchanged)."""

    def append(self, item, ignore_index=True):
        super().append(item)
        return self


# ---------------------------------------------------------------------------
# Authors' cleaning and normalisation (data_cleaning.ipynb), per record
# ---------------------------------------------------------------------------
def as_numbers(x):
    """Values arrive as lists of floats; '-' or anything else means missing."""
    if isinstance(x, (list, tuple)):
        try:
            return [float(v) for v in x]
        except (TypeError, ValueError):
            return None
    if isinstance(x, (int, float)):
        return [float(x)]
    return None


def first_name(names):
    if isinstance(names, (list, tuple)) and names:
        return str(names[0])
    if isinstance(names, str) and names != "-":
        return names
    return None


def prefix_exponent(units):
    """Power of ten in a CDE unit string, e.g. '(10^-6.0) * Kelvin^(-1.0)  Volt^(1.0)' -> -6."""
    found = re.findall(r"\(10\^(\-?\d\d?).0\)", units or "")
    return int(found[0]) if found else 0


def temperatures_K(rec):
    """Authors' rule: a room-temperature mention wins (295 K); else Celsius and
    Fahrenheit are converted; no temperature value at all also becomes 295 K."""
    if rec.get("room_temperature") not in (None, "-"):
        return [ROOM_TEMPERATURE_K]
    temps = as_numbers(rec.get("temp_value"))
    if not temps:
        return [ROOM_TEMPERATURE_K]
    units = rec.get("temp_units") or ""
    if units == "Celsius^(1.0)":
        return [t + 273 for t in temps]
    if units == "Fahrenheit^(1.0)":
        return [(t - 32) * 5 / 9 + 273 for t in temps]
    return temps


def thermal_type(specifier):
    """Authors' tagging (thermal_tagging); 'lattice' rules are checked last and win."""
    x = specifier or ""
    tag = "total"
    if "el" in x or "κe" in x or "κ_e" in x or "λe" in x or "λ_e" in x:
        tag = "electronic"
    if "p" in x or "L" in x or "la" in x or "κl" in x or "κ_l" in x:
        tag = "lattice"
    return tag


def clean(rec):
    """Return (normalised record, None) or (None, reason it was dropped).

    Filters, in the authors' order: compound name with letters and < 80 chars;
    zero value; temperature-gradient excerpts below 290 K; compound name with
    'temp'; temperature equal to a process temperature; temperature outside
    0-2500 K; negative PF; ZT below 1e-18."""
    model = rec.get("model")
    if model not in MODEL_PROPERTY:
        return None, f"unknown model {model!r}"
    name = first_name(rec.get("compound_name"))
    if not name or not any(c in ascii_letters for c in name):
        return None, "compound name without letters"
    if len(name) > 79:
        return None, "compound name longer than 79 characters"
    values = as_numbers(rec.get("value"))
    if not values:
        return None, "no numeric value"
    exp = prefix_exponent(rec.get("units"))
    values = [v * 10 ** exp for v in values]
    if values == [0.0]:
        return None, "zero value"
    if model == "Resistivity":
        values = [1.0 / v for v in values]
    temps = temperatures_K(rec)
    t_avg = sum(temps) / len(temps)
    excerpt = str(rec.get("excerpt") or "")
    if re.search("(temperature (difference|gradient))|Δ", excerpt) and t_avg < 290:
        return None, "temperature difference or gradient"
    if "temp" in name:
        return None, "compound name contains 'temp'"
    temp_value, process = rec.get("temp_value"), rec.get("process")
    if isinstance(temp_value, (list, tuple)) and temp_value and isinstance(process, str) and process != "-":
        if str(temp_value[0]).split(".")[0] in process:
            return None, "temperature is a process temperature"
    if t_avg < 0 or t_avg > 2500:
        return None, "temperature outside 0-2500 K"
    avg = sum(values) / len(values)
    if model == "PF" and avg < 0:
        return None, "negative PF"
    if model == "ZT" and avg < 1e-18:
        return None, "ZT below 1e-18"
    return {"model": model, "name": name.strip(), "values": values, "temps": temps,
            "specifier": rec.get("specifier"), "excerpt": excerpt}, None


def to_prediction(sample_id, norm):
    prop = MODEL_PROPERTY[norm["model"]]
    factor = TO_CANONICAL[prop]
    vals = sorted(v * factor for v in norm["values"])
    p = {f: None for f in PREDICTION_FIELDS}
    p.update({
        "sample_id": sample_id, "property": prop, "material": norm["name"],
        "value": vals[0], "value_max": vals[-1] if len(vals) > 1 else None,
        "qualifier": "range" if len(vals) > 1 else None,
        "T_K": round(sum(norm["temps"]) / len(norm["temps"]), 3),
        "kappa_type": thermal_type(norm["specifier"]) if prop == "kappa" else None,
        "flags": [], "evidence": norm["excerpt"] or None,
    })
    return p


def dedupe_key(rec):
    return json.dumps(rec, sort_keys=True, default=str)


def jsonable(x):
    return json.loads(json.dumps(x, default=str))


# ---------------------------------------------------------------------------
# Running te_parse
# ---------------------------------------------------------------------------
def load_te():
    try:
        from chemdataextractor import Document
        from chemdataextractor.model.units import thermoelectric_models as tm
        from chemdataextractor.split_and_stitch.new_parsing import te_parse
    except ImportError as e:
        raise SystemExit(f"ChemDataExtractor-TE is not importable ({e}); see chem_data_extractor/README.md")
    models = {name: getattr(tm, name) for name in MODEL_ORDER}
    return Document, models, te_parse


def extract_paragraph(text, Document, models, te_parse):
    """All te_parse records for one paragraph, one Document per property model,
    as the authors ran it (one model per pass)."""
    records = []
    for name in MODEL_ORDER:
        d = Document(text)
        d.models = models[name]
        found = RecordList()
        te_parse(d, found, [], filename="paragraph", title="-", given_model=models[name])
        records.extend(found)
    # authors: df.drop_duplicates() on the raw rows
    seen, unique = set(), []
    for r in records:
        k = dedupe_key(r)
        if k not in seen:
            seen.add(k)
            unique.append(r)
    return unique


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def package_info():
    import chemdataextractor
    import pandas
    root = Path(chemdataextractor.__file__).resolve().parent
    h = hashlib.sha256()
    for f in sorted(root.rglob("*.py")):
        h.update(str(f.relative_to(root)).encode())
        h.update(f.read_bytes())
    return {"chemdataextractor_path": str(root), "chemdataextractor_py_sha256": h.hexdigest(),
            "pandas": pandas.__version__}


def run(split, data_dir="evaluation/data", out_root="results", run_id=None, te_commit=None, limit=None):
    inp = Path(data_dir) / split / "inputs.jsonl"
    rows = [json.loads(l) for l in open(inp, encoding="utf-8") if l.strip()]
    if limit:
        rows = rows[:limit]
    run_id = run_id or f"{split}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    out = Path(out_root) / "cde" / run_id
    if out.exists():
        raise SystemExit(f"{out} exists; runs are never overwritten")
    Document, models, te_parse = load_te()
    (out / "raw").mkdir(parents=True)
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    t0 = time.time()
    n_ok = n_failed = n_preds = n_invalid = n_raw = 0
    dropped = {}
    with open(out / "predictions.jsonl", "w", encoding="utf-8") as fp, \
         open(out / "paragraph_status.jsonl", "w", encoding="utf-8") as fs, \
         open(out / "raw" / "te_records.jsonl", "w", encoding="utf-8") as fr:
        for i, row in enumerate(rows, start=1):
            sid = row["sample_id"]
            try:
                recs = extract_paragraph(row["text"], Document, models, te_parse)
            except Exception as e:  # recorded per paragraph; the run continues
                fs.write(json.dumps({"sample_id": sid, "status": "error", "n_predictions": 0,
                                     "error": repr(e)[:500]}) + "\n")
                n_failed += 1
                continue
            preds = []
            for r in recs:
                norm, reason = clean(r)
                fr.write(json.dumps({"sample_id": sid, "kept": norm is not None, "drop_reason": reason,
                                     "record": jsonable(r)}, ensure_ascii=False) + "\n")
                n_raw += 1
                if norm is None:
                    dropped[reason] = dropped.get(reason, 0) + 1
                    continue
                preds.append(to_prediction(sid, norm))
            for p in preds:
                n_invalid += bool(validate_prediction(p))
                fp.write(json.dumps(p, ensure_ascii=False) + "\n")
            fs.write(json.dumps({"sample_id": sid, "status": "ok", "n_predictions": len(preds),
                                 "error": None}) + "\n")
            n_ok += 1
            n_preds += len(preds)
            if i % 10 == 0:
                print(f"  {i}/{len(rows)} paragraphs, {n_preds} predictions")
    wall = round(time.time() - t0, 1)
    meta = {
        "method_id": "M1",
        "method_name": "ChemDataExtractor thermoelectric parsers (Sierepeklis & Cole 2022)",
        "run_id": run_id, "split": split,
        "code_version": {"predict_sha256": sha256_file(__file__),
                         "thermoelectricsdb_commit": te_commit, **package_info()},
        "config": {"models": MODEL_ORDER, "room_temperature_K": ROOM_TEMPERATURE_K,
                   "unit_factors_to_canonical": TO_CANONICAL, "limit": limit},
        "model_id": None, "model_params": None,
        "input_file": str(Path("evaluation/data") / split / "inputs.jsonl"),
        "input_sha256": sha256_file(inp),
        "started_at": started, "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "wall_seconds": wall,
        "n_paragraphs": n_ok + n_failed, "n_ok": n_ok, "n_failed": n_failed,
        "n_predictions": n_preds, "n_invalid_predictions": n_invalid,
        "n_raw_records": n_raw, "dropped_by_cleaning": dropped,
        "n_model_calls": 0, "input_tokens": None, "output_tokens": None, "cost_usd": 0.0,
        "price_table": None,
        "hardware": {"python": platform.python_version(), "machine": platform.machine(),
                     "system": platform.system()},
        "capabilities": CAPABILITIES,
    }
    (out / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("run_id", "n_paragraphs", "n_failed", "n_predictions",
                                           "n_invalid_predictions", "n_raw_records", "dropped_by_cleaning",
                                           "wall_seconds")}, indent=2, ensure_ascii=False))
    print(f"-> {out}")
    return out


# ---------------------------------------------------------------------------
# Self-test: known sentences through the whole chain (CDE + cleaning + mapping)
# ---------------------------------------------------------------------------
SELFTEST = [
    ("The SnSe crystal shows a ZT of 2.6 at 923 K.", "ZT", 2.6, 923),
    ("SbCrSe3 has a thermal conductivity of 0.56 W m-1 K-1 at 900 K.", "kappa", 0.56, 900),
    ("The Seebeck coefficient of Bi2Te3 is 200 μV K-1 at 300 K.", "S_uVK", 200.0, 300),
    ("The electrical conductivity of PbTe is 1000 S cm-1 at 300 K.", "sigma", 1e5, 300),
    ("The electrical resistivity of Cu2Se is 10 μΩ m at 323 K.", "sigma", 1e5, 323),
    ("The power factor of SnSe reaches 10 μW cm-1 K-2 at 800 K.", "PF", 10.0, 800),
]


def selftest():
    Document, models, te_parse = load_te()
    failures = 0
    for text, prop, value, t in SELFTEST:
        preds = []
        for r in extract_paragraph(text, Document, models, te_parse):
            norm, reason = clean(r)
            if norm:
                preds.append(to_prediction("T", norm))
        hit = [p for p in preds if p["property"] == prop and abs(p["value"] - value) <= 0.01 * value
               and abs(p["T_K"] - t) <= 1]
        status = "ok" if hit else "MISS"
        failures += not hit
        print(f"[{status}] {text}\n        expected {prop}={value} at {t} K; got "
              f"{[(p['property'], p['value'], p['T_K'], p['material']) for p in preds]}")
    print(f"{len(SELFTEST) - failures}/{len(SELFTEST)} self-test sentences give the expected record")
    return failures


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run M1 (ChemDataExtractor thermoelectric parsers)")
    ap.add_argument("--split", choices=["dev", "test"])
    ap.add_argument("--data", default="evaluation/data")
    ap.add_argument("--out", default="results")
    ap.add_argument("--run-id")
    ap.add_argument("--te-commit", help="commit of github.com/odysie/thermoelectricsdb used")
    ap.add_argument("--limit", type=int, help="first N paragraphs only (trial run)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        sys.exit(1 if selftest() else 0)
    if not args.split:
        ap.error("--split is required unless --selftest")
    run(args.split, args.data, args.out, args.run_id, args.te_commit, args.limit)


if __name__ == "__main__":
    main()
