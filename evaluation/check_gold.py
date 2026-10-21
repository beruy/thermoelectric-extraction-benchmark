"""
Check a hand-edited gold CSV before scoring.

Usage (from the project root):
    python -m evaluation.check_gold --split dev
    python -m evaluation.check_gold --split dev --gold path/to/file.csv

Reports: wrong or missing columns, unknown sample ids, invalid property codes,
non-numeric or comma-separated numbers, core records without a value,
paragraphs without any row, and duplicate (sample_id, record_no) pairs.
Exit code 0 = no problems, 1 = problems found.
"""

import argparse
import csv
import json
import sys
from collections import Counter
from pathlib import Path

from evaluation.schema import GOLD_RECORD_FIELDS
from evaluation.score import load_gold


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check a gold CSV")
    ap.add_argument("--split", required=True, choices=["dev", "test"])
    ap.add_argument("--data", default="evaluation/data")
    ap.add_argument("--gold")
    args = ap.parse_args(argv)

    data = Path(args.data)
    gold = Path(args.gold or data / args.split / "gold" / "gold_records.csv")
    if not gold.exists():
        sys.exit(f"not found: {gold}")
    with open(data / args.split / "private" / "sample_key.jsonl", encoding="utf-8") as f:
        key_ids = {json.loads(line)["sample_id"] for line in f if line.strip()}

    problems = []
    with open(gold, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        rows = list(reader)
    missing_cols = [c for c in GOLD_RECORD_FIELDS if c not in header]
    extra_cols = [c for c in header if c not in GOLD_RECORD_FIELDS + ["text"]]
    if missing_cols:
        problems.append(f"missing columns: {missing_cols}")
    if extra_cols:
        problems.append(f"unexpected columns (shifted row or typo?): {extra_cols}")
    for i, r in enumerate(rows, start=2):
        if None in r:  # more cells than header columns: broken quoting
            problems.append(f"row {i}: more cells than columns (check quotes in 'text')")
    # Duplicate (sample_id, record_no) rows are reported by load_gold, as in scoring.

    records, load_problems = load_gold(gold, key_ids)
    problems += load_problems

    by_prop = Counter(r["property"] for r in records)
    print(f"{gold}: {len(rows)} rows, {len({r.get('sample_id') for r in rows})} paragraphs, "
          f"{len(records)} records {dict(by_prop)}")
    if problems:
        print(f"{len(problems)} problem(s):")
        for p in problems:
            print("  -", p)
        sys.exit(1)
    print("OK")


if __name__ == "__main__":
    main()
