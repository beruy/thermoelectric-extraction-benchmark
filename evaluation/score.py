"""
Score one method run against the gold standard (PROTOCOL.md §6-7).

Usage (from the project root):
    python -m evaluation.score --split test --run results/regex/<run_id>

Reads
    evaluation/data/<split>/gold/gold_records.csv      gold (long format)
    evaluation/data/<split>/private/sample_key.jsonl   strata, scope, weights
    <run>/predictions.jsonl, <run>/paragraph_status.jsonl, <run>/run.json
Writes
    <run>/scores/<split>_<timestamp>.json and .md      (never overwrites)

Two kinds of numbers are reported and labelled as such:
    sample-level   unweighted; describes exactly the annotated paragraphs
    corpus-level   weighted by 1/pi (Hajek); estimates the in-scope paragraphs
                   of the split's papers
"""

import argparse
import csv
import json
import random
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from evaluation.schema import (ALL_PROPERTIES, CORE_PROPERTIES, EXTENDED_PROPERTIES,
                               NO_RECORD, validate_prediction, validate_record_values, is_finite_number)

# Scoring parameters (PROTOCOL.md §7.2).
VALUE_REL_TOL = 0.01
CARRIER_REL_TOL = 0.05
T_TOL_K = 1.0
T_TOL_STATUS = "decided (PROTOCOL.md §7.2, 2026-10-19)"
RT_RANGE_K = (293.0, 300.0)
# Gold "room temperature" (T_K empty): the primary rule also accepts a numeric
# prediction in RT_RANGE_K (bounds included); the strict sensitivity rule accepts
# only an empty prediction (--rt-strict).
RT_ACCEPT_NUMERIC = True
RT_RE = re.compile(r"room[\s-]*temp|\bRT\b|ambient", re.I)
LEVELS = ("L1", "L2", "L3")
STRONG_KAPPA = {"lattice", "electronic", "bipolar"}
UNIT_FACTORS = [10.0 ** e for e in (-6, -4, -2, 2, 4, 6)]

ELEMENTS = set("""H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu
Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm
Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np
Pu""".split())


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def _num(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        if not is_finite_number(x):
            raise ValueError("expected a finite number, not bool/NaN/Infinity")
        return x
    s = str(x).strip().replace("−", "-")
    if not s:
        return None
    if "," in s:
        # A comma may be a decimal separator (Turkish locale) or a thousands
        # separator; guessing would silently change values, so refuse.
        raise ValueError(f"{s!r}: use '.' as decimal separator and no thousands separator")
    value = float(s)
    if not is_finite_number(value):
        raise ValueError("expected a finite number, not NaN/Infinity")
    return value


def _str(x):
    if x is None:
        return None
    s = str(x).strip()
    return s or None


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def load_gold(path, key_ids):
    rows, problems = [], []
    seen_rows = {}  # (sample_id, record_no) -> first CSV row number
    with open(path, encoding="utf-8-sig") as f:
        for i, r in enumerate(csv.DictReader(f), start=2):
            sid = _str(r.get("sample_id"))
            prop = _str(r.get("property"))
            if sid not in key_ids:
                problems.append(f"row {i}: unknown sample_id {sid!r}")
                continue
            # A duplicated row would add a second gold record and silently lower
            # recall, so a repeated (sample_id, record_no) stops scoring.
            key = (sid, _str(r.get("record_no")))
            if key in seen_rows:
                problems.append(f"row {i}: duplicate (sample_id, record_no) {key} "
                                f"(first in row {seen_rows[key]})")
                continue
            seen_rows[key] = i
            if prop is None:
                problems.append(f"row {i}: empty property (use {NO_RECORD} for no record)")
                continue
            if prop not in ALL_PROPERTIES + [NO_RECORD]:
                problems.append(f"row {i}: property {prop!r} not allowed")
                continue
            try:
                rec = {
                    "sample_id": sid, "property": prop,
                    "material": _str(r.get("material")),
                    "value": _num(r.get("value")), "value_max": _num(r.get("value_max")),
                    "T_K": _num(r.get("T_K")), "T_as_written": _str(r.get("T_as_written")),
                    "kappa_type": _str(r.get("kappa_type")), "qualifier": _str(r.get("qualifier")),
                    "origin": _str(r.get("origin")), "context": _str(r.get("context")),
                    "doping_text": _str(r.get("doping_text")),
                    "carrier_conc_cm3": _num(r.get("carrier_conc_cm3")),
                    "aliases": [a.strip() for a in (r.get("material_aliases") or "").split(";")
                                if a.strip()],
                }
            except ValueError as e:
                problems.append(f"row {i}: not a number ({e})")
                continue
            if prop in CORE_PROPERTIES and rec["value"] is None:
                problems.append(f"row {i}: core property without value")
                continue
            violations = validate_record_values(rec)
            if violations:
                problems.extend(f"row {i}: {error}" for error in violations)
                continue
            rows.append(rec)
    annotated = {r["sample_id"] for r in rows}
    missing = sorted(key_ids - annotated)
    if missing:
        problems.append(f"{len(missing)} sampled paragraphs have no gold row "
                        f"(first: {missing[:5]}); every paragraph needs ≥1 row, {NO_RECORD} if empty")
    return [r for r in rows if r["property"] != NO_RECORD], problems


# ---------------------------------------------------------------------------
# Normalization and match criteria
# ---------------------------------------------------------------------------
def norm_material(s):
    """Safe formatting normalization only (PROTOCOL.md §6.3): Unicode NFKC
    (subscripts -> digits), whitespace and markup characters removed.
    Letter case, amounts, compositions and sample labels are kept."""
    if not s:
        return None
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"[\s_{}$]", "", s)
    return s or None


def parse_formula(s):
    """Element -> fraction of total, or None if s is not a plain formula."""
    s = norm_material(s)
    if not s or not re.fullmatch(r"(?:[A-Z][a-z]?\d*(?:\.\d+)?)+", s):
        return None
    amounts = Counter()
    for el, n in re.findall(r"([A-Z][a-z]?)(\d*(?:\.\d+)?)", s):
        if el not in ELEMENTS:
            return None
        amounts[el] += float(n) if n else 1.0
    total = sum(amounts.values())
    return {el: a / total for el, a in amounts.items()} if total else None


def material_ok(pred, gold, stoich=False):
    p = norm_material(pred.get("material"))
    targets = [gold.get("material")] + gold.get("aliases", [])
    targets = [norm_material(t) for t in targets if t]
    if not targets:
        return p is None
    if p in targets:
        return True
    if stoich and p:
        fp = parse_formula(p)
        if fp:
            for t in targets:
                ft = parse_formula(t)
                if ft and ft.keys() == fp.keys() and all(abs(ft[k] - fp[k]) <= 0.01 for k in ft):
                    return True
    return False


def close(p, g, rel):
    if p is None or g is None:
        return p is None and g is None
    if g == 0:
        return p == 0
    return abs(p - g) <= rel * abs(g)


def value_ok(pred, gold):
    if not close(pred.get("value"), gold.get("value"), VALUE_REL_TOL):
        return False
    return close(pred.get("value_max"), gold.get("value_max"), VALUE_REL_TOL)


def kappa_ok(pred, gold):
    if gold["property"] != "kappa":
        return True
    g = gold.get("kappa_type") if gold.get("kappa_type") in STRONG_KAPPA else "total"
    p = pred.get("kappa_type") if pred.get("kappa_type") in STRONG_KAPPA else "total"
    return g == p


def temp_ok(pred, gold):
    pt, gt = pred.get("T_K"), gold.get("T_K")
    if gt is not None:
        return pt is not None and abs(pt - gt) <= T_TOL_K
    if gold.get("T_as_written") and RT_RE.search(gold["T_as_written"]):
        return pt is None or (RT_ACCEPT_NUMERIC and RT_RANGE_K[0] <= pt <= RT_RANGE_K[1])
    return pt is None


def elements_in(text):
    return {t for t in re.findall(r"[A-Z][a-z]?", text or "") if t in ELEMENTS}


def doping_ok(pred, gold):
    if gold.get("carrier_conc_cm3") is not None:
        return close(pred.get("carrier_conc_cm3"), gold["carrier_conc_cm3"], CARRIER_REL_TOL)
    ge = elements_in(gold.get("doping_text"))
    return bool(ge) and ge == elements_in(pred.get("doping_text"))


def compatible(pred, gold, level, stoich=False):
    if gold["property"] == "doping":
        ok = doping_ok(pred, gold)
        return ok and (level != "L3" or material_ok(pred, gold, stoich))
    ok = value_ok(pred, gold) and kappa_ok(pred, gold)
    if level in ("L2", "L3"):
        ok = ok and temp_ok(pred, gold)
    if level == "L3":
        ok = ok and material_ok(pred, gold, stoich)
    return ok


# ---------------------------------------------------------------------------
# One-to-one matching (maximum bipartite matching, Kuhn's algorithm)
# ---------------------------------------------------------------------------
def max_matching(preds, golds, edge):
    adj = [[j for j, g in enumerate(golds) if edge(p, g)] for p in preds]
    owner = [-1] * len(golds)

    def augment(i, seen):
        for j in adj[i]:
            if not seen[j]:
                seen[j] = True
                if owner[j] == -1 or augment(owner[j], seen):
                    owner[j] = i
                    return True
        return False

    for i in range(len(preds)):
        augment(i, [False] * len(golds))
    return [(owner[j], j) for j in range(len(golds)) if owner[j] != -1]


def dedupe(preds):
    seen, out, dropped = set(), [], 0
    for p in preds:
        k = (p.get("property"), p.get("value"), p.get("value_max"), p.get("T_K"),
             norm_material(p.get("material")), p.get("kappa_type"), p.get("doping_text"),
             p.get("carrier_conc_cm3"))
        if k in seen:
            dropped += 1
            continue
        seen.add(k)
        out.append(p)
    return out, dropped


# ---------------------------------------------------------------------------
# Per-paragraph counts
# ---------------------------------------------------------------------------
INVALID_OTHER = "_invalid_property"  # bucket for invalid records with an unknown property code


def paragraph_counts(preds, golds, props, stoich=False, invalid=()):
    """{(prop, level): [tp, fp, fn]} for one paragraph, plus matched L3 pairs.

    `preds` must be contract-valid. `invalid` records never match anything;
    they are counted as false positives of their property, or of the
    INVALID_OTHER bucket if their property code is unknown."""
    out, pairs = {}, []
    for prop in props:
        if prop == INVALID_OTHER:
            n = sum(1 for p in invalid if p.get("property") not in ALL_PROPERTIES)
            for level in LEVELS:
                out[(prop, level)] = [0, n, 0]
            continue
        P = [p for p in preds if p.get("property") == prop]
        G = [g for g in golds if g["property"] == prop]
        n_bad = sum(1 for p in invalid if p.get("property") == prop)
        for level in LEVELS:
            m = max_matching(P, G, lambda p, g, lv=level: compatible(p, g, lv, stoich))
            out[(prop, level)] = [len(m), len(P) - len(m) + n_bad, len(G) - len(m)]
            if level == "L3":
                pairs += [(P[i], G[j]) for i, j in m]
    return out, pairs


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def prf(tp, fp, fn):
    """Precision, recall, F1.

    F1 = 2TP / (2TP + FP + FN), so a method with no predictions on gold
    records gets F1 = 0 (not undefined). Precision is undefined (None) only
    when there are no predictions; recall only when there are no gold records."""
    p = tp / (tp + fp) if tp + fp else None
    r = tp / (tp + fn) if tp + fn else None
    denom = 2 * tp + fp + fn
    f = 2 * tp / denom if denom else None
    return p, r, f


def aggregate(per_para, weights, props, level, sids=None):
    tp = fp = fn = 0.0
    for sid in (sids if sids is not None else per_para):
        counts = per_para[sid]
        w = weights[sid]
        for prop in props:
            a, b, c = counts.get((prop, level), (0, 0, 0))
            tp += w * a
            fp += w * b
            fn += w * c
    return tp, fp, fn


def bootstrap(per_para, weights, paper_of, props, level, reps, seed):
    """Paper-level bootstrap CI (2.5 / 97.5 percentiles). Every resample is
    kept; resamples in which a metric is undefined are counted, not dropped
    silently."""
    # Per-paper weighted totals are computed once; a resample only sums them.
    per_paper = defaultdict(lambda: [0.0, 0.0, 0.0])
    for sid in per_para:
        t = aggregate(per_para, weights, props, level, [sid])
        acc = per_paper[paper_of[sid]]
        for i in range(3):
            acc[i] += t[i]
    papers = sorted(per_paper)
    rng = random.Random(seed)
    vals = {"precision": [], "recall": [], "f1": []}
    undefined = Counter()
    for _ in range(reps):
        tp = fp = fn = 0.0
        for _ in papers:
            a, b, c = per_paper[rng.choice(papers)]
            tp, fp, fn = tp + a, fp + b, fn + c
        for name, v in zip(("precision", "recall", "f1"), prf(tp, fp, fn)):
            if v is None:
                undefined[name] += 1
            else:
                vals[name].append(v)

    def ci(xs):
        if not xs:
            return None
        xs = sorted(xs)
        return [xs[int(0.025 * (len(xs) - 1))], xs[int(round(0.975 * (len(xs) - 1)))]]

    return {"reps": reps, **{k: ci(v) for k, v in vals.items()},
            "undefined_resamples": dict(undefined)}


def level_entry(counts, weights, ones, paper_of, props, level, reps, seed):
    entry = {}
    for label, w in (("sample_level", ones), ("corpus_level", weights)):
        tp, fp, fn = aggregate(counts, w, props, level)
        p, r, f = prf(tp, fp, fn)
        entry[label] = {"precision": p, "recall": r, "f1": f, "tp": tp, "fp": fp, "fn": fn,
                        "ci95_paper_bootstrap": bootstrap(counts, w, paper_of, props, level,
                                                          reps, seed)}
    return entry


def diagnostics(preds_by_sid, golds_by_sid):
    unit, sign = Counter(), Counter()
    for sid, preds in preds_by_sid.items():
        golds = golds_by_sid.get(sid, [])
        for p in preds:
            prop, v = p.get("property"), p.get("value")
            if prop not in CORE_PROPERTIES or v is None:
                continue
            same = [g for g in golds if g["property"] == prop]
            if any(close(v, g["value"], VALUE_REL_TOL) for g in same):
                continue
            if any(close(v * f, g["value"], VALUE_REL_TOL) for g in same for f in UNIT_FACTORS):
                unit[prop] += 1
            elif prop == "S_uVK" and any(close(-v, g["value"], VALUE_REL_TOL) for g in same):
                sign[prop] += 1
    return {"unit_errors": dict(unit), "sign_errors": dict(sign)}


def attribute_accuracy(pairs, field):
    judged = [(p.get(field), g.get(field)) for p, g in pairs if g.get(field)]
    if not judged:
        return None
    return {"n": len(judged), "accuracy": sum(a == b for a, b in judged) / len(judged)}


# ---------------------------------------------------------------------------
# Integrity checks: any failure stops scoring
# ---------------------------------------------------------------------------
class ScoringError(Exception):
    """Gold or run is incomplete or inconsistent; no score is produced."""

    def __init__(self, errors):
        super().__init__("\n".join(errors))
        self.errors = errors


def sha256_file(path):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def check_run(split, run, data_dir, key_by, status, raw_preds):
    errors = []
    if run.get("split") != split:
        errors.append(f"run.json split is {run.get('split')!r}, scoring split is {split!r}")
    inp = Path(data_dir) / split / "inputs.jsonl"
    expected = sha256_file(inp)
    if run.get("input_sha256") != expected:
        errors.append(f"run.json input_sha256 {run.get('input_sha256')!r} does not match "
                      f"{inp} ({expected}); the run was not produced from this input")
    missing = sorted(set(key_by) - set(status))
    if missing:
        errors.append(f"{len(missing)} paragraphs have no line in paragraph_status.jsonl "
                      f"(first: {missing[:5]}); the run is incomplete")
    unknown_status = sorted(set(status) - set(key_by))
    if unknown_status:
        errors.append(f"paragraph_status.jsonl has unknown sample_ids: {unknown_status[:5]}")
    bad_status = sorted(s for s, v in status.items()
                        if v.get("status") not in ("ok", "error", "timeout"))
    if bad_status:
        errors.append(f"invalid status values for: {bad_status[:5]}")
    bad_ids = sum(1 for p in raw_preds if not isinstance(p.get("sample_id"), str))
    if bad_ids:
        errors.append(f"{bad_ids} prediction records have a missing or non-string sample_id")
        return errors
    unknown = sorted({p.get("sample_id") for p in raw_preds} - set(key_by))
    if unknown:
        errors.append(f"predictions for unknown sample_ids: {unknown[:5]}")
    actual_counts = Counter(p.get("sample_id") for p in raw_preds)
    for sid, entry in status.items():
        declared = entry.get("n_predictions")
        if type(declared) is not int or declared < 0:
            errors.append(f"{sid}: n_predictions must be a non-negative integer")
        elif declared != actual_counts[sid]:
            errors.append(f"{sid}: n_predictions={declared}, but predictions.jsonl contains "
                          f"{actual_counts[sid]} records")
    return errors


# ---------------------------------------------------------------------------
# Main scoring
# ---------------------------------------------------------------------------
def score(split, run_dir, data_dir, gold_path=None, reps=2000, seed=7):
    """Score one run. Raises ScoringError if gold or run fails a check."""
    data_dir, run_dir = Path(data_dir), Path(run_dir)
    key = load_jsonl(data_dir / split / "private" / "sample_key.jsonl")
    key_by = {k["sample_id"]: k for k in key}
    gold_path = Path(gold_path or data_dir / split / "gold" / "gold_records.csv")
    if not gold_path.exists():
        raise ScoringError([f"gold file not found: {gold_path}"])
    golds, gold_problems = load_gold(gold_path, set(key_by))

    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    status_rows = load_jsonl(run_dir / "paragraph_status.jsonl")
    repeated = [sid for sid, n in Counter(s["sample_id"] for s in status_rows).items() if n > 1]
    if repeated:
        raise ScoringError([f"duplicate paragraph status for sample_id {sid!r}" for sid in repeated])
    status = {s["sample_id"]: s for s in status_rows}
    raw_preds = load_jsonl(run_dir / "predictions.jsonl")

    errors = [f"gold: {p}" for p in gold_problems]
    errors += [f"run: {e}" for e in check_run(split, run, data_dir, key_by, status, raw_preds)]
    if errors:
        raise ScoringError(errors)

    capabilities = run.get("capabilities") or ALL_PROPERTIES
    failed = {sid for sid in key_by if status[sid]["status"] != "ok"}
    preds_by_sid, invalid_by_sid, golds_by_sid = defaultdict(list), defaultdict(list), defaultdict(list)
    ignored_failed = dup_total = 0
    for p in raw_preds:
        sid = p["sample_id"]
        if sid in failed:
            ignored_failed += 1
        elif validate_prediction(p):
            invalid_by_sid[sid].append(p)
        else:
            preds_by_sid[sid].append(p)
    for sid in list(preds_by_sid):
        preds_by_sid[sid], d = dedupe(preds_by_sid[sid])
        dup_total += d
    for g in golds:
        golds_by_sid[g["sample_id"]].append(g)

    in_scope = [sid for sid in key_by if key_by[sid]["in_scope"]]
    control = [sid for sid in key_by if not key_by[sid]["in_scope"]]
    weights = {sid: key_by[sid]["weight"] for sid in key_by}
    ones = {sid: 1.0 for sid in key_by}
    paper_of = {sid: key_by[sid]["paper_id"] for sid in key_by}

    def per_paragraph(props, stoich=False):
        counts, pairs = {}, []
        for sid in in_scope:
            c, pr = paragraph_counts(preds_by_sid.get(sid, []), golds_by_sid.get(sid, []),
                                     props, stoich, invalid_by_sid.get(sid, []))
            counts[sid] = c
            pairs += pr
        return counts, pairs

    supported_core = [p for p in CORE_PROPERTIES if p in capabilities]
    field_sets = {
        "core_all": CORE_PROPERTIES + [INVALID_OTHER],   # unsupported properties count as misses
        "core_supported_only": supported_core + [INVALID_OTHER],
        "extended_doping": EXTENDED_PROPERTIES if "doping" in capabilities else [],
    }
    results, l3_pairs = {}, []
    for name, props in field_sets.items():
        if not [p for p in props if p != INVALID_OTHER]:
            results[name] = "not supported"
            continue
        counts, pairs = per_paragraph(props)
        if name == "core_all":
            l3_pairs = pairs
        results[name] = {level: level_entry(counts, weights, ones, paper_of, props, level,
                                            reps, seed) for level in LEVELS}

    # Per-property breakdown (L3) with gold record counts and CIs
    counts, _ = per_paragraph(CORE_PROPERTIES + EXTENDED_PROPERTIES)
    per_prop = {}
    for prop in CORE_PROPERTIES + EXTENDED_PROPERTIES:
        n_gold = sum(1 for sid in in_scope for g in golds_by_sid.get(sid, [])
                     if g["property"] == prop)
        if prop not in capabilities:
            per_prop[prop] = {"status": "not supported", "n_gold_records": n_gold}
        else:
            per_prop[prop] = {"n_gold_records": n_gold,
                              **level_entry(counts, weights, ones, paper_of, [prop], "L3",
                                            reps, seed)}

    # Secondary: stoichiometry-aware material matching (sensitivity only)
    s_counts, _ = per_paragraph(CORE_PROPERTIES + [INVALID_OTHER], stoich=True)
    stoich = level_entry(s_counts, weights, ones, paper_of, CORE_PROPERTIES + [INVALID_OTHER],
                         "L3", reps, seed)

    n_invalid = sum(len(v) for v in invalid_by_sid.values())
    return {
        "split": split, "run": str(run_dir), "method_id": run.get("method_id"),
        "run_id": run.get("run_id"),
        "scored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "gold_file": str(gold_path), "gold_sha256": sha256_file(gold_path),
        "input_sha256": run.get("input_sha256"),
        "parameters": {"value_rel_tol": VALUE_REL_TOL, "carrier_rel_tol": CARRIER_REL_TOL,
                       "t_tol_K": T_TOL_K, "t_tol_status": T_TOL_STATUS,
                       "room_temperature_range_K": RT_RANGE_K,
                       "room_temperature_rule": "lenient (empty or 293-300 K)" if RT_ACCEPT_NUMERIC else "strict (empty only)",
                       "bootstrap_reps": reps,
                       "bootstrap_seed": seed, "material_matching": "safe formatting only",
                       "f1_definition": "2TP / (2TP + FP + FN)"},
        "labels": {"sample_level": "unweighted; the annotated paragraphs themselves",
                   "corpus_level": "weighted by 1/pi (Hajek); in-scope paragraphs of the split's papers"},
        "n_paragraphs": {"total": len(key_by), "in_scope": len(in_scope), "control": len(control),
                         "failed": len(failed)},
        "n_gold_records_in_scope": sum(len(golds_by_sid.get(sid, [])) for sid in in_scope),
        "capabilities": capabilities,
        "scores": results,
        "per_property_L3": per_prop,
        "secondary": {
            "stoichiometry_aware_L3_core": stoich,
            "origin_accuracy_on_L3_matches": attribute_accuracy(l3_pairs, "origin"),
            "context_accuracy_on_L3_matches": attribute_accuracy(l3_pairs, "context"),
            "diagnostics": diagnostics({s: preds_by_sid[s] for s in in_scope if s in preds_by_sid},
                                       golds_by_sid),
            "duplicates_collapsed": dup_total,
            "invalid_prediction_records": n_invalid,
            "invalid_records_note": "contract-invalid records never match; counted as false positives",
            "predictions_ignored_on_failed_paragraphs": ignored_failed,
        },
        "control_stratum": {"paragraphs": len(control),
                            "gold_records": sum(len(golds_by_sid.get(s, [])) for s in control),
                            "predictions": sum(len(preds_by_sid.get(s, [])) for s in control)},
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------
def fmt(x):
    return "–" if x is None else f"{x:.3f}"


def fmt_ci(entry, metric="f1"):
    ci = entry["ci95_paper_bootstrap"][metric]
    return f"{fmt(ci[0])}–{fmt(ci[1])}" if ci else "–"


def to_markdown(s):
    lines = [f"# Scores: {s['method_id']} / {s['run_id']} on {s['split']}", "",
             f"Scored {s['scored_at']}. F1 = 2TP/(2TP+FP+FN). Temperature tolerance "
             f"±{s['parameters']['t_tol_K']} K ({s['parameters']['t_tol_status']}); room temperature: "
             f"{s['parameters']['room_temperature_rule']}.", "",
             f"Paragraphs: {s['n_paragraphs']}. Gold records in scope: "
             f"{s['n_gold_records_in_scope']}. Invalid prediction records (counted as FP): "
             f"{s['secondary']['invalid_prediction_records']}.", "",
             "Sample level = unweighted, the annotated paragraphs. "
             "Corpus level = weighted 1/π, in-scope paragraphs of the split's papers. "
             "CIs: 95 % paper-level bootstrap.", "",
             "| Field set | Level | Sample P | Sample R | Sample F1 | Sample F1 CI | "
             "Corpus P | Corpus R | Corpus F1 | Corpus F1 CI |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for name, block in s["scores"].items():
        if block == "not supported":
            lines.append(f"| {name} | – | not supported | | | | | | | |")
            continue
        for level, e in block.items():
            a, c = e["sample_level"], e["corpus_level"]
            lines.append(f"| {name} | {level} | {fmt(a['precision'])} | {fmt(a['recall'])} | "
                         f"{fmt(a['f1'])} | {fmt_ci(a)} | {fmt(c['precision'])} | "
                         f"{fmt(c['recall'])} | {fmt(c['f1'])} | {fmt_ci(c)} |")
    lines += ["", "| Property (L3) | Gold records | Sample F1 | Sample F1 CI | Corpus F1 | Corpus F1 CI |",
              "|---|---|---|---|---|---|"]
    for prop, row in s["per_property_L3"].items():
        if row.get("status"):
            lines.append(f"| {prop} | {row['n_gold_records']} | not supported | | | |")
        else:
            a, c = row["sample_level"], row["corpus_level"]
            lines.append(f"| {prop} | {row['n_gold_records']} | {fmt(a['f1'])} | {fmt_ci(a)} | "
                         f"{fmt(c['f1'])} | {fmt_ci(c)} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    global T_TOL_K, RT_ACCEPT_NUMERIC
    ap = argparse.ArgumentParser(description="Score a method run (PROTOCOL.md §7)")
    ap.add_argument("--split", required=True, choices=["dev", "test"])
    ap.add_argument("--run", required=True, help="results/<method>/<run_id>")
    ap.add_argument("--data", default="evaluation/data")
    ap.add_argument("--gold", help="gold CSV (default: data/<split>/gold/gold_records.csv)")
    ap.add_argument("--t-tol", type=float, default=T_TOL_K)
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--rt-strict", action="store_true",
                    help="sensitivity: gold room temperature matches only an empty prediction")
    args = ap.parse_args(argv)
    T_TOL_K = args.t_tol
    RT_ACCEPT_NUMERIC = not args.rt_strict

    try:
        s = score(args.split, args.run, args.data, args.gold, args.bootstrap, args.seed)
    except ScoringError as e:
        print(f"NOT SCORED: {len(e.errors)} problem(s); nothing was written.")
        for err in e.errors:
            print("  -", err)
        raise SystemExit(1)

    out = Path(args.run) / "scores"
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = out / f"{args.split}_{stamp}"
    if base.with_suffix(".json").exists():
        raise SystemExit(f"{base}.json exists; not overwriting")
    base.with_suffix(".json").write_text(json.dumps(s, indent=2), encoding="utf-8")
    base.with_suffix(".md").write_text(to_markdown(s), encoding="utf-8")
    print(to_markdown(s))


if __name__ == "__main__":
    main()
