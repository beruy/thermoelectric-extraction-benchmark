"""
Error diagnosis for one scored method run (development aid, dev split only).

Usage (from the project root):
    python -m evaluation.diagnose --split dev --run results/regex/<run_id>

For every paragraph and property, predictions and gold records are matched
one-to-one on property + value (level L1, as in score.py). Each matched pair is
then checked for temperature (L2) and material (L3); each unmatched record is
classified. Writes, never overwriting:
    <run>/diagnostics/<split>_<timestamp>.md     summary tables
    <run>/diagnostics/<split>_<timestamp>.csv    one row per error case

This file is not part of the scored evaluation (PROTOCOL.md §7). It must not be
run on the test split before all methods are frozen (§9).
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from evaluation import score as S
from evaluation.schema import CORE_PROPERTIES, EXTENDED_PROPERTIES, validate_prediction

PROPS = CORE_PROPERTIES + EXTENDED_PROPERTIES


def l1_ok(p, g):
    if g["property"] == "doping":
        return S.doping_ok(p, g)
    return S.value_ok(p, g) and S.kappa_ok(p, g)


def staged_matching(ps, gs):
    """Pair predictions and gold records on property + value, preferring pairs
    that also agree on temperature and material: match at L3 first, then L2
    among the rest, then L1. Matching on value alone could pair two equal
    values of different materials and report a spurious material error."""
    pairs, free_p, free_g = [], list(range(len(ps))), list(range(len(gs)))
    for level in ("L3", "L2", "L1"):
        sub_p, sub_g = [ps[i] for i in free_p], [gs[j] for j in free_g]
        edge = (lambda p, g: l1_ok(p, g)) if level == "L1" else \
               (lambda p, g, lv=level: S.compatible(p, g, lv))
        for a, b in S.max_matching(sub_p, sub_g, edge):
            pairs.append((free_p[a], free_g[b]))
        used_p, used_g = {i for i, _ in pairs}, {j for _, j in pairs}
        free_p = [i for i in free_p if i not in used_p]
        free_g = [j for j in free_g if j not in used_g]
    return pairs


def material_error(p, g, other_gold_materials):
    pm, gm = S.norm_material(p.get("material")), S.norm_material(g.get("material"))
    targets = [S.norm_material(t) for t in [g.get("material")] + g.get("aliases", []) if t]
    if not gm:
        return "material given where the text names none"
    if not pm:
        return "material missing"
    if any(pm in t or t in pm for t in targets):
        return "partial name (one contains the other)"
    if pm in other_gold_materials:
        return "linked to another material of the paragraph"
    if S.material_ok(p, g, stoich=True):
        return "same composition, different notation"
    return "wrong material"


def temp_error(p, g):
    pt, gt = p.get("T_K"), g.get("T_K")
    rt = bool(g.get("T_as_written") and S.RT_RE.search(g["T_as_written"]))
    if gt is not None and pt is None:
        return "temperature missing"
    if gt is None and not rt and pt is not None:
        return "temperature given where the text gives none"
    if rt:
        return "room temperature not recognised"
    return "wrong temperature"


def diagnose(split, run_dir, data_dir="evaluation/data"):
    run_dir, data = Path(run_dir), Path(data_dir) / split
    key = {k["sample_id"]: k for k in S.load_jsonl(data / "private" / "sample_key.jsonl")}
    text = {r["sample_id"]: r["text"] for r in S.load_jsonl(data / "inputs.jsonl")}
    golds, problems = S.load_gold(data / "gold" / "gold_records.csv", set(key))
    if problems:
        raise SystemExit("gold has problems; run evaluation.check_gold first")
    status = {s["sample_id"]: s["status"] for s in S.load_jsonl(run_dir / "paragraph_status.jsonl")}
    preds = [p for p in S.load_jsonl(run_dir / "predictions.jsonl")
             if status.get(p["sample_id"]) == "ok" and not validate_prediction(p)]

    G, P = defaultdict(list), defaultdict(list)
    for g in golds:
        G[g["sample_id"]].append(g)
    for p in preds:
        P[p["sample_id"]].append(p)

    cases, counts = [], Counter()
    n_gold = Counter(g["property"] for g in golds if key[g["sample_id"]]["in_scope"])
    for sid in key:
        gold_mats = {S.norm_material(g.get("material")) for g in G[sid] if g.get("material")}
        for prop in PROPS:
            gs = [g for g in G[sid] if g["property"] == prop]
            ps = [p for p in P[sid] if p.get("property") == prop]
            pairs = staged_matching(ps, gs)
            mp, mg = {i for i, _ in pairs}, {j for _, j in pairs}

            def add(kind, reason, p=None, g=None):
                counts[(prop, kind, reason)] += 1
                cases.append({
                    "sample_id": sid, "stratum": key[sid]["stratum"], "property": prop,
                    "error": kind, "reason": reason,
                    "gold_value": g and g.get("value"), "pred_value": p and p.get("value"),
                    "gold_material": g and g.get("material"), "pred_material": p and p.get("material"),
                    "gold_T": g and (g.get("T_K") or g.get("T_as_written")), "pred_T": p and p.get("T_K"),
                    "text": text[sid][:300]})

            for i, j in pairs:
                p, g = ps[i], gs[j]
                if prop != "doping" and not S.temp_ok(p, g):
                    add("L2 temperature", temp_error(p, g), p, g)
                if not S.material_ok(p, g):
                    add("L3 material", material_error(p, g, gold_mats - {S.norm_material(g.get('material'))}), p, g)
            for j, g in enumerate(gs):
                if j not in mg:
                    reason = "value found with a different number" if len(ps) > len(mp) else "value not found"
                    add("L1 missed (FN)", reason, None, g)
            for i, p in enumerate(ps):
                if i in mp:
                    continue
                if not G[sid] or all(g["property"] == "NONE" for g in G[sid]):
                    reason = "paragraph has no gold record"
                elif any(l1_ok({**p, "property": g["property"]}, g) for g in G[sid] if g["property"] != prop):
                    reason = "value belongs to another property"
                elif gs:
                    reason = "extra or wrong value for this property"
                else:
                    reason = "property not in gold for this paragraph"
                add("L1 spurious (FP)", reason, p, None)
    return cases, counts, n_gold, len(preds)


def to_markdown(split, run_dir, cases, counts, n_gold, n_pred):
    lines = [f"# Error diagnosis: {run_dir.parent.name} / {run_dir.name} on {split}", "",
             "Development aid, not a score (PROTOCOL.md §7). Records are paired on property + value, "
             "preferring pairs that also agree on temperature and material; temperature and material "
             "errors are counted on the pairs that remain.", "",
             f"Gold records: {sum(n_gold.values())} (in scope). Valid predictions: {n_pred}.", ""]
    by_kind = Counter()
    for (prop, kind, reason), n in counts.items():
        by_kind[(kind, reason)] += n
    lines += ["## All properties", "", "| Error | Reason | Count |", "|---|---|---|"]
    for (kind, reason), n in sorted(by_kind.items(), key=lambda x: (x[0][0], -x[1])):
        lines.append(f"| {kind} | {reason} | {n} |")
    lines += ["", "## By property", "", "| Property | Error | Reason | Count |", "|---|---|---|---|"]
    for (prop, kind, reason), n in sorted(counts.items(), key=lambda x: (PROPS.index(x[0][0]), x[0][1], -x[1])):
        lines.append(f"| {prop} | {kind} | {reason} | {n} |")
    mat = [c for c in cases if c["error"] == "L3 material"]
    if mat:
        lines += ["", "## Material errors (all cases)", "",
                  "| Sample | Property | Gold material | Predicted material | Reason |", "|---|---|---|---|---|"]
        for c in mat:
            lines.append(f"| {c['sample_id']} | {c['property']} | {c['gold_material'] or '—'} | "
                         f"{c['pred_material'] or '—'} | {c['reason']} |")
    return "\n".join(lines) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="Error diagnosis for one method run")
    ap.add_argument("--split", required=True, choices=["dev", "test"])
    ap.add_argument("--run", required=True)
    ap.add_argument("--data", default="evaluation/data")
    args = ap.parse_args(argv)
    run_dir = Path(args.run)
    cases, counts, n_gold, n_pred = diagnose(args.split, run_dir, args.data)
    out = run_dir / "diagnostics"
    out.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md, csv_path = out / f"{args.split}_{stamp}.md", out / f"{args.split}_{stamp}.csv"
    md.write_text(to_markdown(args.split, run_dir, cases, counts, n_gold, n_pred), encoding="utf-8")
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(cases[0]) if cases else ["sample_id"])
        w.writeheader()
        w.writerows(cases)
    print(json.dumps({"cases": len(cases), "markdown": str(md), "csv": str(csv_path)}, indent=2))


if __name__ == "__main__":
    main()
