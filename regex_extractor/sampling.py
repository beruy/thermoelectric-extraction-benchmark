"""
Stratified, blind sampling of paragraphs for gold-standard annotation.

Scope
-----
The evaluation scope is defined by ONE explicit rule (extractor.SCOPE_RULE /
extractor.in_scope): a thermoelectric keyword AND at least one digit. It is
applied to every paragraph before stratification, so the scope boundary is
also a stratum boundary:

  in scope   ZT, S_uVK, PF, kappa, sigma, doping   regex hit; highest-priority property
             in_scope_no_hit                        no regex hit (where misses are likely)
  out of     out_of_scope                           control: every paragraph failing the
  scope                                             rule, with or without regex hits

In-scope precision/recall are computed on in-scope units only, and every
method's output is filtered with the same rule. The control stratum is
reported separately (how many gold records exist outside the scope).

Inclusion probabilities
-----------------------
* max_per_paper = 0 (default): stratified simple random sampling without
  replacement. pi = n_h / N_h exactly, weight = N_h / n_h.
* max_per_paper > 0: at most k paragraphs of one paper per stratum. The cap
  makes pi paragraph-specific, so pi is estimated by replaying the same drawing
  procedure with many seeds (Monte Carlo; the realized draw is counted as one
  replication). weight = 1 / pi_hat.

The total sample never exceeds n, and every non-empty stratum gets at least one
paragraph, so no paragraph has zero inclusion probability.

Weights are written per sampled paragraph to sample_key.jsonl. Use them for
weighted (Horvitz-Thompson / Hajek) estimates; paragraphs of one paper are
correlated, so compute confidence intervals with a paper-level bootstrap.

Blind: the annotation sheet contains only paragraph text. Strata, scope flags,
weights and regex outputs go to the key file.
"""

import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path

from .extractor import SCOPE_RULE, in_scope
from .schema import GOLD_FIELDS

PRIORITY = ["ZT", "S_uVK", "PF", "kappa", "sigma", "doping"]
IN_SCOPE_NO_HIT = "in_scope_no_hit"
OUT_OF_SCOPE = "out_of_scope"
STRATA_ORDER = PRIORITY + [IN_SCOPE_NO_HIT, OUT_OF_SCOPE]


def _load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _inv(p):
    return (1.0 / p) if p else None


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs)) if xs else None


def _primary_property(props):
    for p in PRIORITY:
        if p in props:
            return p
    return None


def _allocate(sizes, n, none_frac, control_frac, min_per_stratum):
    """Sample size per stratum.

    Guarantees:
      * the total never exceeds n (or the number of units, if smaller);
      * every non-empty stratum gets at least 1 unit, so no unit has a zero
        inclusion probability (raises if n is too small for that);
      * no stratum gets more than its population.
    Targets: fixed shares for the no-hit and control strata, the rest proportional
    to stratum size with a floor of min_per_stratum. Targets are only targets:
    the budget is filled greedily towards them and never beyond n.
    """
    nonempty = [s for s in STRATA_ORDER if sizes[s]]
    n_eff = min(n, sum(sizes.values()))
    if n_eff < len(nonempty):
        raise ValueError(f"n={n} is too small: {len(nonempty)} non-empty strata each need at least "
                         f"one paragraph, otherwise their units have zero inclusion probability.")

    target = {s: 0 for s in STRATA_ORDER}
    target[OUT_OF_SCOPE] = round(n_eff * control_frac)
    target[IN_SCOPE_NO_HIT] = round(n_eff * none_frac)
    pos = [s for s in PRIORITY if sizes[s]]
    n_pos = max(0, n_eff - target[OUT_OF_SCOPE] - target[IN_SCOPE_NO_HIT])
    # Floors never eat into the fixed shares: they are scaled to fit inside n_pos.
    floor = min(min_per_stratum, n_pos // len(pos)) if pos else 0
    base = {s: min(floor, sizes[s]) for s in pos}
    rest = n_pos - sum(base.values())
    room_total = sum(sizes[s] - base[s] for s in pos) or 1
    for s in pos:
        target[s] = base[s] + rest * (sizes[s] - base[s]) / room_total

    alloc = {s: (1 if sizes[s] else 0) for s in STRATA_ORDER}
    for _ in range(n_eff - sum(alloc.values())):
        room = [s for s in nonempty if alloc[s] < sizes[s]]
        if not room:
            break
        # stratum furthest below its target; once all targets are met, the one with most room
        best = max(room, key=lambda s: (target[s] - alloc[s], sizes[s] - alloc[s]))
        alloc[best] += 1
    assert sum(alloc.values()) <= n_eff
    return alloc


def _draw(pools, paper_of, alloc, max_per_paper, rng):
    """One realization of the sampling procedure. Returns {stratum: [unit index, ...]}.

    The per-paper cap applies WITHIN each stratum (at most k paragraphs of one
    paper per stratum). Quotas used in one stratum never block another, and
    inside a stratum every unit can be visited first, so every unit of a
    non-empty stratum keeps a non-zero inclusion probability. A stratum may end
    up below its allocation if the cap blocks it; the report shows this."""
    chosen = {}
    for s in STRATA_ORDER:
        pool, k = pools[s], alloc[s]
        picked = []
        if k:
            per_paper = Counter()
            order = rng.sample(pool, len(pool)) if max_per_paper else rng.sample(pool, k)
            for u in order:
                if len(picked) >= k:
                    break
                if max_per_paper and per_paper[paper_of[u]] >= max_per_paper:
                    continue
                per_paper[paper_of[u]] += 1
                picked.append(u)
        chosen[s] = picked
    return chosen


def build_sample(run_dir, out_dir, n=200, none_frac=0.2, control_frac=0.2, min_per_stratum=15,
                 max_per_paper=0, source="auto", seed=42, mc_reps=2000):
    run_dir, out_dir = Path(run_dir), Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    paragraphs = _load_jsonl(run_dir / "paragraphs.jsonl")
    candidates = _load_jsonl(run_dir / "candidates.jsonl")

    # One source per paper, so the same paragraph is not annotated twice
    sources_by_paper = defaultdict(set)
    for p in paragraphs:
        sources_by_paper[p["paper_id"]].add(p["source"])

    def wanted(p):
        if source == "auto":
            return p["source"] == ("html" if "html" in sources_by_paper[p["paper_id"]] else "pdf")
        return p["source"] == source

    cands_by_para = defaultdict(list)
    for c in candidates:
        cands_by_para[(c["paper_id"], c["source"], c["para_id"])].append(c)

    # Units = paragraphs of the evaluation corpus. The scope rule is applied FIRST
    # (recomputed from the text, so older runs are handled the same way), then the
    # in-scope units are stratified by regex result.
    units = [p for p in paragraphs if wanted(p)]
    paper_of = [p["paper_id"] for p in units]
    scope_of = [in_scope(p["text"]) for p in units]
    pools = {s: [] for s in STRATA_ORDER}
    control_with_hits = 0
    for i, p in enumerate(units):
        props = {c["property"] for c in cands_by_para.get((p["paper_id"], p["source"], p["para_id"]), [])}
        if not scope_of[i]:
            pools[OUT_OF_SCOPE].append(i)
            control_with_hits += bool(props)
            continue
        pools[_primary_property(props) or IN_SCOPE_NO_HIT].append(i)
    sizes = {s: len(pools[s]) for s in STRATA_ORDER}

    alloc = _allocate(sizes, n, none_frac, control_frac, min_per_stratum)
    chosen = _draw(pools, paper_of, alloc, max_per_paper, random.Random(seed))
    drawn = {s: len(v) for s, v in chosen.items()}

    # Inclusion probabilities
    never_drawn = None
    if max_per_paper:
        # The realized draw is counted as one replication, so a sampled unit can
        # never get pi_hat = 0.
        hits = Counter()
        for picked in chosen.values():
            hits.update(picked)
        for r in range(mc_reps):
            rep = _draw(pools, paper_of, alloc, max_per_paper, random.Random(f"{seed}-mc-{r}"))
            for picked in rep.values():
                hits.update(picked)
        reps = mc_reps + 1
        pi = {u: hits[u] / reps for picked in chosen.values() for u in picked}
        never_drawn = sum(1 for pool in pools.values() for u in pool if hits[u] == 0)
        design = (f"stratified, per-paper cap {max_per_paper} within each stratum; "
                  f"pi estimated by Monte Carlo ({reps} draws incl. the realized one)")
    else:
        pi = {u: drawn[s] / sizes[s] for s, picked in chosen.items() for u in picked}
        design = "stratified simple random sampling without replacement; pi = n_h / N_h (exact)"

    sample = [(s, u) for s in STRATA_ORDER for u in chosen[s]]
    random.Random(f"{seed}-order").shuffle(sample)   # annotation order must not reveal strata

    # Blind annotation sheet (one row per paragraph; copy the row for extra records)
    with open(out_dir / "gold_annotation_sheet.csv", "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["sample_id", "paper_id", "source", "para_id", "para_kind", "text"] + GOLD_FIELDS)
        for i, (_, u) in enumerate(sample, start=1):
            p = units[u]
            w.writerow([f"S{i:04d}", p["paper_id"], p["source"], p["para_id"], p["kind"], p["text"]]
                       + [""] * len(GOLD_FIELDS))

    # Key (not for the annotator)
    low_pi = 0
    with open(out_dir / "sample_key.jsonl", "w", encoding="utf-8") as f:
        for i, (s, u) in enumerate(sample, start=1):
            p = units[u]
            prob = pi[u]
            if max_per_paper and prob * (mc_reps + 1) < 30:
                low_pi += 1      # weight rests on few MC hits: imprecise
            f.write(json.dumps({
                "sample_id": f"S{i:04d}", "stratum": s, "in_scope": scope_of[u],
                "paper_id": p["paper_id"], "source": p["source"], "para_id": p["para_id"],
                "inclusion_prob": prob, "weight": _inv(prob),
                "regex_candidates": cands_by_para.get((p["paper_id"], p["source"], p["para_id"]), []),
            }, ensure_ascii=False) + "\n")

    n_ctrl = drawn[OUT_OF_SCOPE]
    report = {
        "seed": seed, "n_requested": n, "n_drawn": len(sample),
        "underfilled_strata": {s: {"allocated": alloc[s], "sampled": drawn[s]}
                               for s in STRATA_ORDER if drawn[s] < alloc[s]}, "source_policy": source,
        "design": design,
        "scope_rule": SCOPE_RULE,
        "corpus": ("All paragraphs produced by the reader for one source per paper "
                   "(HTML when available, else PDF). Text the reader does not produce "
                   "(table cells, text lost in PDF parsing, references) is outside the corpus."),
        "units": {"total": len(units), "in_scope": sum(scope_of), "out_of_scope": len(units) - sum(scope_of),
                  "out_of_scope_with_regex_hits": control_with_hits},
        "strata": {s: {"in_scope": s != OUT_OF_SCOPE, "population": sizes[s], "allocated": alloc[s],
                       "sampled": drawn[s],
                       "mean_weight": _mean([_inv(pi[u]) for u in chosen[s]])}
                   for s in STRATA_ORDER},
        "control": {
            "sampled": n_ctrl,
            # If the control sample contains no gold record, the share of out-of-scope
            # paragraphs holding a record is below this bound with 95 % confidence.
            "upper95_share_if_zero_records": (1 - 0.05 ** (1 / n_ctrl)) if n_ctrl else None,
            "upper95_paragraphs_if_zero_records": (sizes[OUT_OF_SCOPE] * (1 - 0.05 ** (1 / n_ctrl)))
            if n_ctrl else None,
        },
        "papers_in_sample": len({units[u]["paper_id"] for _, u in sample}),
        "max_paragraphs_from_one_paper": max(Counter(units[u]["paper_id"] for _, u in sample).values(),
                                             default=0),
    }
    if max_per_paper:
        report["units_with_fewer_than_30_mc_hits"] = low_pi
        # Theoretically 0 (every unit has pi > 0); a positive count means pi is too
        # small for mc_reps to resolve: increase --mc-reps.
        report["population_units_never_drawn_in_mc"] = never_drawn
    (out_dir / "sampling_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
