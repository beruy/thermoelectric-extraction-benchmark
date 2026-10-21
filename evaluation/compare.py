"""
Side-by-side comparison of method runs on one split (PROTOCOL.md §7).

Usage (from the project root):
    python -m evaluation.compare --split dev \
        --run results/regex/<run_id> --run results/claude/<run_id> [--run ...]

The first --run is the reference. For each other run the report gives the
difference in F1 to the reference with a 95 % paired paper-level bootstrap CI:
both methods are scored on the same resampled papers, so the CI reflects the
difference itself, not two separate intervals. Counting is exactly as in
score.py (same matching, dedupe, failed-paragraph and invalid-record rules).

Writes, never overwriting:
    results/comparisons/<split>_<timestamp>.md
    results/comparisons/<split>_<timestamp>.json
"""

import argparse
import json
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from evaluation import score as S
from evaluation.schema import CORE_PROPERTIES, EXTENDED_PROPERTIES, validate_prediction

LEVELS = ("L1", "L2", "L3")
CORE = CORE_PROPERTIES + [S.INVALID_OTHER]


def paragraph_counts_for_run(split, run_dir, data_dir, props, gold_path=None):
    """{sid: {(prop, level): [tp, fp, fn]}} for in-scope paragraphs, counted as score.py does."""
    data_dir, run_dir = Path(data_dir), Path(run_dir)
    key_by = {k["sample_id"]: k for k in S.load_jsonl(data_dir / split / "private" / "sample_key.jsonl")}
    golds, problems = S.load_gold(Path(gold_path) if gold_path else data_dir / split / "gold" / "gold_records.csv",
                                  set(key_by))
    if problems:
        raise SystemExit("gold has problems; run evaluation.check_gold first")
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    status = {s["sample_id"]: s for s in S.load_jsonl(run_dir / "paragraph_status.jsonl")}
    raw = S.load_jsonl(run_dir / "predictions.jsonl")
    errors = S.check_run(split, run, data_dir, key_by, status, raw)
    if errors:
        raise SystemExit(f"{run_dir}: run fails integrity checks; score it first:\n" + "\n".join(errors))
    failed = {sid for sid in key_by if status[sid]["status"] != "ok"}
    preds, invalid, gold_by = defaultdict(list), defaultdict(list), defaultdict(list)
    for p in raw:
        if p["sample_id"] in failed:
            continue
        (invalid if validate_prediction(p) else preds)[p["sample_id"]].append(p)
    for sid in list(preds):
        preds[sid], _ = S.dedupe(preds[sid])
    for g in golds:
        gold_by[g["sample_id"]].append(g)
    counts = {}
    for sid, k in key_by.items():
        if k["in_scope"]:
            counts[sid], _ = S.paragraph_counts(preds.get(sid, []), gold_by.get(sid, []),
                                                props, False, invalid.get(sid, []))
    return counts, run, key_by


def f1_of(counts, weights, props, level, sids):
    return S.prf(*S.aggregate(counts, weights, props, level, sids))[2]


def paired_bootstrap(ref, other, weights, paper_of, props, level, reps, seed):
    """95 % CI of F1(other) - F1(ref) over paper-level resamples, and the
    share of resamples in which other is not better (a one-sided p-like value)."""
    by_paper = defaultdict(list)
    for sid in ref:
        by_paper[paper_of[sid]].append(sid)
    papers = sorted(by_paper)
    rng = random.Random(seed)
    diffs, undefined = [], 0
    for _ in range(reps):
        sids = [s for _ in papers for s in by_paper[rng.choice(papers)]]
        a, b = f1_of(ref, weights, props, level, sids), f1_of(other, weights, props, level, sids)
        if a is None or b is None:
            undefined += 1
            continue
        diffs.append(b - a)
    diffs.sort()
    if not diffs:
        return {"ci95": None, "share_not_better": None, "undefined_resamples": undefined}
    ci = [diffs[int(0.025 * (len(diffs) - 1))], diffs[int(round(0.975 * (len(diffs) - 1)))]]
    return {"ci95": ci, "share_not_better": sum(d <= 0 for d in diffs) / len(diffs),
            "undefined_resamples": undefined}


def paragraph_outcomes(ref, other, level):
    """Per paragraph: errors (fp + fn over core properties) of each method."""
    better = worse = same_err = both_perfect = 0
    for sid in ref:
        ea = sum(v[1] + v[2] for (p, lv), v in ref[sid].items() if lv == level)
        eb = sum(v[1] + v[2] for (p, lv), v in other[sid].items() if lv == level)
        if ea == eb == 0:
            both_perfect += 1
        elif eb < ea:
            better += 1
        elif eb > ea:
            worse += 1
        else:
            same_err += 1
    return {"other_fewer_errors": better, "other_more_errors": worse,
            "same_nonzero_errors": same_err, "both_perfect": both_perfect}


def compare(split, run_dirs, data_dir="evaluation/data", reps=2000, seed=7, gold_path=None):
    props_all = CORE_PROPERTIES + EXTENDED_PROPERTIES
    runs = []
    for rd in run_dirs:
        core, meta, key_by = paragraph_counts_for_run(split, rd, data_dir, CORE, gold_path)
        per_prop, _, _ = paragraph_counts_for_run(split, rd, data_dir, props_all, gold_path)
        runs.append({"dir": str(rd), "meta": meta, "core": core, "per_prop": per_prop})
    weights = {sid: k["weight"] for sid, k in key_by.items()}
    ones = {sid: 1.0 for sid in key_by}
    paper_of = {sid: k["paper_id"] for sid, k in key_by.items()}
    sids = list(runs[0]["core"])
    gold_path = Path(gold_path) if gold_path else Path(data_dir) / split / "gold" / "gold_records.csv"

    out = {"split": split, "compared_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "gold_file": str(gold_path), "gold_sha256": S.sha256_file(gold_path), "bootstrap_reps": reps, "bootstrap_seed": seed,
           "parameters": {"value_rel_tol": S.VALUE_REL_TOL, "carrier_rel_tol": S.CARRIER_REL_TOL,
                          "t_tol_K": S.T_TOL_K, "t_tol_status": S.T_TOL_STATUS,
                          "room_temperature_range_K": list(S.RT_RANGE_K),
                          "room_temperature_rule": "lenient (empty or 293-300 K)" if S.RT_ACCEPT_NUMERIC else "strict (empty only)"},
           "reference": runs[0]["dir"], "runs": []}
    for r in runs:
        m = r["meta"]
        entry = {"run": r["dir"], "method_id": m.get("method_id"), "model_id": m.get("model_id"),
                 "n_failed": m.get("n_failed"), "cost_usd": m.get("cost_usd"),
                 "wall_seconds": m.get("wall_seconds"), "scores": {}, "per_property_L3": {}}
        for label, w in (("sample_level", ones), ("corpus_level", weights)):
            for level in LEVELS:
                p, rc, f = S.prf(*S.aggregate(r["core"], w, CORE, level, sids))
                entry["scores"][f"{label}/{level}"] = {"precision": p, "recall": rc, "f1": f}
        for prop in props_all:
            entry["per_property_L3"][prop] = f1_of(r["per_prop"], ones, [prop], "L3", sids)
        out["runs"].append(entry)
    out["differences"] = []
    ref = runs[0]
    for r in runs[1:]:
        d = {"run": r["dir"], "vs": ref["dir"], "f1_difference": {}, "paragraphs": {}}
        for label, w in (("sample_level", ones), ("corpus_level", weights)):
            for level in LEVELS:
                point = f1_of(r["core"], w, CORE, level, sids) - f1_of(ref["core"], w, CORE, level, sids)
                d["f1_difference"][f"{label}/{level}"] = {
                    "point": point,
                    **paired_bootstrap(ref["core"], r["core"], w, paper_of, CORE, level, reps, seed)}
        for level in LEVELS:
            d["paragraphs"][level] = paragraph_outcomes(ref["core"], r["core"], level)
        out["differences"].append(d)
    return out


def fmt(x, signed=False):
    if x is None:
        return "–"
    return f"{x:+.3f}" if signed else f"{x:.3f}"


def name(entry):
    return f"{entry['method_id']} ({Path(entry['run']).name})"


def to_markdown(c):
    runs = c["runs"]
    head = "| " + " | ".join(name(r) for r in runs) + " |"
    sep = "|---|---|" + "---|" * len(runs)
    lines = [f"# Method comparison on {c['split']}", "",
             f"Compared {c['compared_at']}. Gold {c.get('gold_file', '')} (sha256 {c['gold_sha256'][:12]}…). "
             "Core properties (ZT, S, κ, σ, PF); F1 = 2TP/(2TP+FP+FN). "
             "Sample level = the annotated paragraphs; corpus level = weighted 1/π.", "",
             f"Matching parameters: value tolerance {c['parameters']['value_rel_tol']:.0%}; "
             f"temperature tolerance ±{c['parameters']['t_tol_K']} K, "
             f"{c['parameters']['t_tol_status']}; room temperature: "
             f"**{c['parameters']['room_temperature_rule']}**.", "",
             "## Scores", "", "| Level | Metric " + head, sep]
    for label in ("sample_level", "corpus_level"):
        for level in LEVELS:
            for metric in ("precision", "recall", "f1"):
                vals = " | ".join(fmt(r["scores"][f"{label}/{level}"][metric]) for r in runs)
                lines.append(f"| {label.split('_')[0]} {level} | {metric} | {vals} |")
    lines += ["", "## Per property, L3 F1 (sample level)", "", "| Property " + head,
              "|---|" + "---|" * len(runs)]
    for prop in runs[0]["per_property_L3"]:
        lines.append(f"| {prop} | " + " | ".join(fmt(r["per_property_L3"][prop]) for r in runs) + " |")
    lines += ["", "## Cost and failures", "", "| Run | Model | Failed paragraphs | Cost (USD) |",
              "|---|---|---|---|"]
    for r in runs:
        cost = "–" if r["cost_usd"] is None else format(r["cost_usd"], ".2f")
        lines.append(f"| {name(r)} | {r['model_id'] or '–'} | {r['n_failed']} | {cost} |")
    ref = next(r for r in runs if r["run"] == c["reference"])
    for d in c["differences"]:
        other = next(r for r in runs if r["run"] == d["run"])
        lines += ["", f"## {name(other)} minus {name(ref)}", "",
                  f"Paired paper-level bootstrap, {c['bootstrap_reps']} resamples. "
                  "'Share not better' is the fraction of resamples in which the difference is ≤ 0. "
                  "It describes the bootstrap distribution; it is not a p-value or an error "
                  "probability. A value of 0.000 means none of the resamples.", "",
                  "| Level | F1 difference | 95 % CI | Share not better |", "|---|---|---|---|"]
        for key, v in d["f1_difference"].items():
            ci = f"{fmt(v['ci95'][0], True)} to {fmt(v['ci95'][1], True)}" if v["ci95"] else "–"
            lines.append(f"| {key.replace('_level', '')} | {fmt(v['point'], True)} | {ci} | "
                         f"{fmt(v['share_not_better'])} |")
        lines += ["", "Paragraph outcomes (in-scope paragraphs; errors = FP + FN over core properties):", "",
                  "| Level | Fewer errors | More errors | Same, non-zero | Both perfect |", "|---|---|---|---|---|"]
        for level, o in d["paragraphs"].items():
            lines.append(f"| {level} | {o['other_fewer_errors']} | {o['other_more_errors']} | "
                         f"{o['same_nonzero_errors']} | {o['both_perfect']} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Compare method runs on one split")
    ap.add_argument("--split", required=True, choices=["dev", "test"])
    ap.add_argument("--run", required=True, action="append",
                    help="results/<method>/<run_id>; give two or more, the first is the reference")
    ap.add_argument("--data", default="evaluation/data")
    ap.add_argument("--gold", help="gold CSV (default: data/<split>/gold/gold_records.csv)")
    ap.add_argument("--out", default="results/comparisons")
    ap.add_argument("--bootstrap", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--rt-strict", action="store_true",
                    help="sensitivity: gold room temperature matches only an empty prediction")
    args = ap.parse_args(argv)
    if len(args.run) < 2:
        ap.error("give at least two --run arguments")
    S.RT_ACCEPT_NUMERIC = not args.rt_strict
    c = compare(args.split, args.run, args.data, args.bootstrap, args.seed, args.gold)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md, js = out / f"{args.split}_{stamp}.md", out / f"{args.split}_{stamp}.json"
    if md.exists() or js.exists():
        raise SystemExit(f"{md} exists; comparisons are never overwritten")
    md.write_text(to_markdown(c), encoding="utf-8")
    js.write_text(json.dumps(c, indent=2), encoding="utf-8")
    print(f"-> {md}\n-> {js}")


if __name__ == "__main__":
    main()
