"""
Command-line interface.

    python -m regex_extractor extract --pdf-dir corpus-main --html-dir "Claude outputs/corpus/html" --out regex_output
    python -m regex_extractor sample  --run regex_output --n 200 --out regex_output/gold_sample
"""

import argparse
import csv
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

from .extractor import RegexExtractor, RELEVANCE_RE, in_scope
from .readers import read_document
from .sampling import build_sample
from .schema import CANDIDATE_FIELDS


def _collect(pdf_dir, html_dir, source, limit):
    jobs = []
    if source in ("both", "pdf") and pdf_dir:
        jobs += [("pdf", p) for p in sorted(Path(pdf_dir).glob("*.pdf"))]
    if source in ("both", "html") and html_dir:
        jobs += [("html", p) for p in sorted(Path(html_dir).glob("*.html"))]
    if limit:
        stems = sorted({p.stem for _, p in jobs})[:limit]
        jobs = [j for j in jobs if j[1].stem in stems]
    return jobs


def cmd_extract(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    extractor = RegexExtractor()
    jobs = _collect(args.pdf_dir, args.html_dir, args.source, args.limit)
    if not jobs:
        sys.exit("No input files found. Check --pdf-dir / --html-dir.")

    stats = defaultdict(Counter)
    per_paper = defaultdict(lambda: defaultdict(Counter))
    t0 = time.time()
    with open(out / "paragraphs.jsonl", "w", encoding="utf-8") as fp, \
         open(out / "candidates.jsonl", "w", encoding="utf-8") as fc, \
         open(out / "candidates.csv", "w", newline="", encoding="utf-8-sig") as fcsv, \
         open(out / "errors.jsonl", "w", encoding="utf-8") as fe:
        w = csv.DictWriter(fcsv, fieldnames=CANDIDATE_FIELDS)
        w.writeheader()
        for i, (src, path) in enumerate(jobs, start=1):
            pid = path.stem
            try:
                paras = read_document(path, pdf_backend=args.pdf_backend)
            except Exception as e:  # keep going; record the failure
                fe.write(json.dumps({"paper_id": pid, "source": src, "error": repr(e)}) + "\n")
                stats[src]["read_errors"] += 1
                continue
            stats[src]["documents"] += 1
            per_paper[pid][src]  # register every read document, even with zero candidates
            for para in paras:
                # A paragraph the extractor fails on is still written to
                # paragraphs.jsonl (with zero candidates and the error), so it
                # stays in the sampling pool: method failures must be evaluable.
                extract_error = None
                try:
                    cands = extractor.extract(para["text"])
                except Exception as e:  # one bad paragraph must not stop the batch
                    cands, extract_error = [], repr(e)
                    fe.write(json.dumps({"paper_id": pid, "source": src,
                                         "para_id": para.get("para_id"),
                                         "error": extract_error}) + "\n")
                    stats[src]["extract_errors"] += 1
                props = sorted({c.property for c in cands})
                fp.write(json.dumps({"paper_id": pid, "source": src, **para,
                                     "n_candidates": len(cands), "properties": props,
                                     "extract_error": extract_error,
                                     "relevant": bool(RELEVANCE_RE.search(para["text"])),
                                     "in_scope": in_scope(para["text"])},
                                    ensure_ascii=False) + "\n")
                stats[src]["paragraphs"] += 1
                if cands:
                    stats[src]["paragraphs_with_hits"] += 1
                for c in cands:
                    row = {"paper_id": pid, "source": src, "para_id": para["para_id"],
                           "para_kind": para["kind"], **c.to_dict()}
                    fc.write(json.dumps(row, ensure_ascii=False) + "\n")
                    w.writerow({**row, "flags": ";".join(row["flags"])})
                    stats[src][f"cand_{c.property}"] += 1
                    per_paper[pid][src][c.property] += 1
            if i % 25 == 0 or i == len(jobs):
                print(f"[{i}/{len(jobs)}] {src} {pid}  ({time.time() - t0:.0f}s)", flush=True)

    # HTML vs PDF on papers that have both (first look at PDF-extraction loss)
    paired = {pid: d for pid, d in per_paper.items() if "html" in d and "pdf" in d}
    pair_summary = {}
    for prop in ["ZT", "S_uVK", "kappa", "sigma", "PF", "doping"]:
        h = sum(d["html"][prop] for d in paired.values())
        p = sum(d["pdf"][prop] for d in paired.values())
        pair_summary[prop] = {"html": h, "pdf": p}
    # Papers where HTML has hits but the PDF has none: the PDF-loss signal.
    pdf_total_loss = sorted(pid for pid, d in paired.items()
                            if sum(d["html"].values()) > 0 and sum(d["pdf"].values()) == 0)

    summary = {
        "inputs": {"pdf_dir": args.pdf_dir, "html_dir": args.html_dir, "source": args.source,
                   "pdf_backend": args.pdf_backend},
        "by_source": {k: dict(v) for k, v in stats.items()},
        "papers_with_any_candidate": sum(1 for d in per_paper.values() if any(d.values())),
        "paired_papers": len(paired),
        "paired_candidate_counts": pair_summary,
        "paired_html_hits_pdf_none": len(pdf_total_loss),
        "paired_html_hits_pdf_none_ids": pdf_total_loss,
        "seconds": round(time.time() - t0, 1),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


def cmd_sample(args):
    report = build_sample(args.run, args.out or Path(args.run) / "gold_sample", n=args.n,
                          none_frac=args.none_frac, control_frac=args.control_frac,
                          min_per_stratum=args.min_per_stratum, max_per_paper=args.max_per_paper,
                          source=args.source, seed=args.seed, mc_reps=args.mc_reps)
    print(json.dumps(report, indent=2))


def cmd_test(args):
    """Print candidates for one file or a text snippet (debugging)."""
    ex = RegexExtractor()
    if args.text:
        paras = [{"para_id": "t", "kind": "body", "text": args.text}]
    else:
        paras = read_document(args.file, pdf_backend=args.pdf_backend)
    for p in paras:
        cands = ex.extract(p["text"])
        if not cands and not args.all:
            continue
        print(f"\n--- {p['para_id']} [{p['kind']}] {p['text'][:200]}")
        for c in cands:
            print(f"  {c.property:6} {c.value!s:>10} {c.unit:13} T={c.T_K} mat={c.material} "
                  f"q={c.qualifier} dop={c.dopant} flags={c.flags}  <{c.value_text}>")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="regex_extractor",
                                 description="Regex baseline for thermoelectric data extraction")
    sub = ap.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="Run the extractor over a corpus")
    e.add_argument("--pdf-dir", default="corpus-main")
    e.add_argument("--html-dir", default=None, help="arXiv HTML folder (optional)")
    e.add_argument("--source", choices=["both", "pdf", "html"], default="both")
    e.add_argument("--pdf-backend", choices=["auto", "pymupdf", "pypdf"], default="auto")
    e.add_argument("--limit", type=int, default=0, help="Only the first N papers (for testing)")
    e.add_argument("--out", default="regex_output")
    e.set_defaults(func=cmd_extract)

    s = sub.add_parser("sample", help="Draw a stratified blind sample for gold annotation")
    s.add_argument("--run", default="regex_output", help="Output folder of 'extract'")
    s.add_argument("--out", default=None)
    s.add_argument("--n", type=int, default=200)
    s.add_argument("--none-frac", type=float, default=0.2,
                   help="Share for in-scope paragraphs with NO regex hit (for recall)")
    s.add_argument("--control-frac", "--rest-frac", dest="control_frac", type=float, default=0.2,
                   help="Share for the out-of-scope control stratum (default 0.2 = 40 of 200)")
    s.add_argument("--min-per-stratum", type=int, default=15)
    s.add_argument("--max-per-paper", type=int, default=0,
                   help="0 = no cap (exact weights). >0 caps paragraphs per paper; "
                        "inclusion probabilities are then estimated by Monte Carlo")
    s.add_argument("--mc-reps", type=int, default=2000,
                   help="Monte Carlo replays for inclusion probabilities (only with a cap)")
    s.add_argument("--source", choices=["auto", "html", "pdf"], default="auto",
                   help="auto = HTML when the paper has it, else PDF")
    s.add_argument("--seed", type=int, default=42)
    s.set_defaults(func=cmd_sample)

    t = sub.add_parser("test", help="Show candidates for one file or a text snippet")
    g = t.add_mutually_exclusive_group(required=True)
    g.add_argument("--file")
    g.add_argument("--text")
    t.add_argument("--pdf-backend", choices=["auto", "pymupdf", "pypdf"], default="auto")
    t.add_argument("--all", action="store_true", help="Also print paragraphs without hits")
    t.set_defaults(func=cmd_test)

    args = ap.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
