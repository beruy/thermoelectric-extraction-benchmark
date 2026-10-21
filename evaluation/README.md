# evaluation — shared benchmark infrastructure

Method-independent contract, data split, samples and scorer for the
thermoelectric extraction comparison. Rules: `PROTOCOL.md`.

| File | Role |
|---|---|
| `schema.py` | contract: input fields, prediction fields, gold fields, canonical units |
| `sample.py` | paper-level dev/test split and stratified paragraph samples |
| `score.py` | scorer (matching, L1–L3, sample- and corpus-level scores, bootstrap CIs) |
| `tests/` | scorer unit tests |
| `manifests/` | frozen M0 hashes |
| `data/<split>/inputs.jsonl` | **the only file a method reads** |
| `data/<split>/annotation/` | blind annotation sheet (annotator only) |
| `data/<split>/gold/` | completed gold records (scorer only) |
| `data/<split>/private/` | sampling key, weights, report, reliability subset (scorer only) |

## Commands (from the `arxiv` folder)

```bash
# Split and samples: already drawn on 2026-10-09; refuses to redraw without --force
python -m evaluation.sample

# Tests
python -m unittest discover -s evaluation/tests -t .

# Score a run once gold_records.csv exists
python -m evaluation.score --split dev --run results/regex/<run_id>
```

## Annotating

Fill `data/<split>/annotation/annotation_sheet.csv` (one row per record; copy
a row for further records, keep `sample_id`, increase `record_no`; `NONE` for a
paragraph without records) and save it as `data/<split>/gold/gold_records.csv`.
Do not look at any method output before the annotation is finished.
