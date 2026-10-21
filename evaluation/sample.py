"""
Paper-level dev/test split and stratified paragraph samples (PROTOCOL.md §3-4).

The sampling frame and strata come from the frozen regex run (M0): every
paragraph in regex_output/paragraphs.jsonl, stratified by M0 hits and the scope
rule. The stratified design itself is regex_extractor.sampling.build_sample,
applied separately to the papers of each split.

Usage (from the project root):
    python -m evaluation.sample --frame regex_output --out evaluation/data

Outputs per split (evaluation/data/<split>/):
    inputs.jsonl                      method input: sample_id, paper_id, para_id, text
    annotation/annotation_sheet.csv   blind sheet for the annotator (long format)
    private/sample_key.jsonl          strata, scope, weights   (scorer only)
    private/sampling_report.json      design and stratum sizes (scorer only)
    private/reliability_subset.json   test only: pre-selected 20 % for a second annotation
plus evaluation/data/split.json and evaluation/data/manifest.json.

Methods read only inputs.jsonl. Nothing under private/ or annotation/ is given
to a method.
"""

import argparse
import csv
import hashlib
import json
import random
import re
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from evaluation.schema import GOLD_RECORD_FIELDS, INPUT_FIELDS

SPLITS = ("dev", "test")
PREFIX = {"dev": "D", "test": "T"}


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------------------
# Paper identity: all files / versions of one paper share a group key
# ---------------------------------------------------------------------------
def paper_group(paper_id, doi_to_arxiv):
    """Group key for a file stem. arXiv versions (vN) collapse to one key; a
    DOI-named file whose DOI belongs to an arXiv paper joins that paper."""
    pid = paper_id.lower()
    if pid in doi_to_arxiv:
        pid = doi_to_arxiv[pid]
    return re.sub(r"v\d+$", "", pid)


def load_doi_to_arxiv(meta_csv):
    mapping = {}
    if meta_csv and Path(meta_csv).exists():
        with open(meta_csv, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("doi") and row.get("arxiv_id"):
                    mapping[row["doi"].lower().replace("/", "_")] = row["arxiv_id"].lower()
    return mapping


def make_split(paper_ids, dev_frac, seed, doi_to_arxiv):
    groups = defaultdict(list)
    for pid in paper_ids:
        groups[paper_group(pid, doi_to_arxiv)].append(pid)
    keys = sorted(groups)
    rng = random.Random(seed)
    rng.shuffle(keys)
    n_dev = round(len(keys) * dev_frac)
    split_of_group = {k: ("dev" if i < n_dev else "test") for i, k in enumerate(keys)}
    split_of_paper = {pid: split_of_group[k] for k, pids in groups.items() for pid in pids}
    return split_of_paper, groups, split_of_group


# ---------------------------------------------------------------------------
# Sampling within one split (reuses the frozen M0 stratified design)
# ---------------------------------------------------------------------------
def sample_split(split, papers, paragraphs, candidates, out_dir, n, seed, design):
    from regex_extractor.sampling import build_sample

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        write_jsonl(tmp / "paragraphs.jsonl", [p for p in paragraphs if p["paper_id"] in papers])
        write_jsonl(tmp / "candidates.jsonl", [c for c in candidates if c["paper_id"] in papers])
        build_sample(tmp, tmp / "sample", n=n, seed=seed, **design)
        key = load_jsonl(tmp / "sample" / "sample_key.jsonl")
        report = json.loads((tmp / "sample" / "sampling_report.json").read_text(encoding="utf-8"))

    text_of = {(p["paper_id"], p["source"], p["para_id"]): p for p in paragraphs}
    inputs, keys, sheet = [], [], []
    for i, k in enumerate(key, start=1):
        sid = f"{PREFIX[split]}{i:04d}"
        para = text_of[(k["paper_id"], k["source"], k["para_id"])]
        inputs.append({"sample_id": sid, "paper_id": k["paper_id"],
                       "para_id": k["para_id"], "text": para["text"]})
        keys.append({"sample_id": sid, "split": split, "paper_id": k["paper_id"],
                     "source": k["source"], "para_id": k["para_id"], "para_kind": para.get("kind"),
                     "stratum": k["stratum"], "in_scope": k["in_scope"],
                     "inclusion_prob": k["inclusion_prob"], "weight": k["weight"],
                     "m0_candidates": k.get("regex_candidates")})
        sheet.append(sid)

    assert [list(r) for r in inputs][0] == INPUT_FIELDS
    write_jsonl(out_dir / "inputs.jsonl", inputs)
    write_jsonl(out_dir / "private" / "sample_key.jsonl", keys)
    report.update({"split": split, "sample_id_prefix": PREFIX[split],
                   "note": "Strata are defined by M0 (regex) hits; every paragraph of the split "
                           "has a known non-zero inclusion probability."})
    (out_dir / "private" / "sampling_report.json").write_text(json.dumps(report, indent=2),
                                                              encoding="utf-8")

    # Blind annotation sheet, long format: one prefilled row per paragraph.
    # Extra records: copy the row, keep sample_id, increase record_no.
    sheet_path = out_dir / "annotation" / "annotation_sheet.csv"
    sheet_path.parent.mkdir(parents=True, exist_ok=True)
    with open(sheet_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["text"] + GOLD_RECORD_FIELDS)
        for row in inputs:
            w.writerow([row["text"], row["sample_id"], 1] + [""] * (len(GOLD_RECORD_FIELDS) - 2))
    return keys, report


def reliability_subset(keys, frac, seed):
    """Stratified pre-selection of frac of the test sample for a second annotator."""
    rng = random.Random(seed)
    by_stratum = defaultdict(list)
    for k in keys:
        by_stratum[k["stratum"]].append(k["sample_id"])
    chosen = []
    for s in sorted(by_stratum):
        ids = sorted(by_stratum[s])
        m = max(1, round(len(ids) * frac))
        chosen += sorted(rng.sample(ids, m))
    return chosen


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--frame", default="regex_output", help="frozen M0 run folder")
    ap.add_argument("--arxiv-meta", default="Claude outputs/corpus/metadata.csv")
    ap.add_argument("--out", default="evaluation/data")
    ap.add_argument("--dev-frac", type=float, default=0.30)
    ap.add_argument("--split-seed", type=int, default=20261009)
    ap.add_argument("--dev-n", type=int, default=100)
    ap.add_argument("--test-n", type=int, default=200)
    ap.add_argument("--dev-seed", type=int, default=1009)
    ap.add_argument("--test-seed", type=int, default=2009)
    ap.add_argument("--reliability-frac", type=float, default=0.20)
    ap.add_argument("--reliability-seed", type=int, default=3009)
    ap.add_argument("--force", action="store_true", help="overwrite an existing split")
    ap.add_argument("--reuse-split", help="split.json of an earlier draw: keep its paper -> split "
                                          "assignment exactly (used when the frame is rebuilt)")
    args = ap.parse_args(argv)

    frame, out = Path(args.frame), Path(args.out)
    if (out / "split.json").exists() and not args.force:
        raise SystemExit(f"{out/'split.json'} exists. The split is drawn once; use --force only "
                         "if no annotation or method run depends on it.")

    paragraphs = load_jsonl(frame / "paragraphs.jsonl")
    candidates = load_jsonl(frame / "candidates.jsonl")
    doi_to_arxiv = load_doi_to_arxiv(args.arxiv_meta)
    paper_ids = sorted({p["paper_id"] for p in paragraphs})
    split_of, groups, split_of_group = make_split(paper_ids, args.dev_frac, args.split_seed,
                                                  doi_to_arxiv)
    if args.reuse_split:
        previous = json.loads(Path(args.reuse_split).read_text(encoding="utf-8"))["papers"]
        missing = sorted(set(paper_ids) - set(previous))
        if missing:
            raise SystemExit(f"papers not in {args.reuse_split}: {missing[:10]}")
        changed = sorted(pid for pid in paper_ids if previous[pid] != split_of[pid])
        if changed:
            raise SystemExit(f"split differs from {args.reuse_split} for {changed[:10]}")
        print(f"split identical to {args.reuse_split} for all {len(paper_ids)} papers")

    design = dict(none_frac=0.2, control_frac=0.2, min_per_stratum=15, max_per_paper=0,
                  source="auto", mc_reps=2000)
    sizes = {"dev": args.dev_n, "test": args.test_n}
    seeds = {"dev": args.dev_seed, "test": args.test_seed}
    reports, all_keys = {}, {}
    for split in SPLITS:
        papers = {p for p, s in split_of.items() if s == split}
        keys, report = sample_split(split, papers, paragraphs, candidates, out / split,
                                    sizes[split], seeds[split], design)
        reports[split], all_keys[split] = report, keys

    rel = reliability_subset(all_keys["test"], args.reliability_frac, args.reliability_seed)
    (out / "test" / "private" / "reliability_subset.json").write_text(json.dumps({
        "purpose": "independent second annotation (PROTOCOL.md §5.3); annotator still open",
        "frac": args.reliability_frac, "seed": args.reliability_seed,
        "stratified_by": "stratum", "sample_ids": rel}, indent=2), encoding="utf-8")

    # --- checks -----------------------------------------------------------
    for split in SPLITS:
        for k in all_keys[split]:
            assert split_of[k["paper_id"]] == split, (split, k["paper_id"])
    dev_groups = {g for g, s in split_of_group.items() if s == "dev"}
    test_groups = {g for g, s in split_of_group.items() if s == "test"}
    assert not dev_groups & test_groups

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    split_doc = {
        "created": now, "protocol": "evaluation/PROTOCOL.md", "dev_frac": args.dev_frac,
        "seed": args.split_seed, "unit": "paper group (arXiv versions and matching DOI files)",
        "frame_files": {str(frame / n): sha256(frame / n)
                        for n in ("paragraphs.jsonl", "candidates.jsonl")},
        "n_groups": {"dev": len(dev_groups), "test": len(test_groups)},
        "n_paragraphs": dict(Counter(split_of[p["paper_id"]] for p in paragraphs)),
        "papers": {pid: split_of[pid] for pid in paper_ids},
    }
    (out / "split.json").write_text(json.dumps(split_doc, indent=2), encoding="utf-8")

    produced = sorted(p for p in out.rglob("*") if p.is_file() and p.name != "manifest.json")
    manifest = {
        "created": now,
        "parameters": {**vars(args), "design": design},
        "samples": {s: {"n": len(all_keys[s]), "papers": len({k['paper_id'] for k in all_keys[s]}),
                        "by_stratum": dict(Counter(k["stratum"] for k in all_keys[s]))}
                    for s in SPLITS},
        "files": {str(p.relative_to(out)): sha256(p) for p in produced},
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"groups": split_doc["n_groups"], "paragraphs": split_doc["n_paragraphs"],
                      "samples": manifest["samples"], "reliability_subset": len(rel)}, indent=2))


if __name__ == "__main__":
    main()
