# regex_extractor — Regex baseline for thermoelectric data

Deterministic, zero-cost candidate extractor for **ZT, Seebeck (S), thermal
conductivity (κ), electrical conductivity (σ), power factor (PF) and doping**.
It is "Baseline 0" of the method comparison and also builds the sampling frame
for the gold standard.

## Install

```bash
pip install pymupdf beautifulsoup4 lxml    # pypdf is used as a fallback if PyMuPDF is missing
```

## Run (from the `arxiv` folder)

```bash
# 1) Extract from all PDFs and the arXiv HTML versions
python -m regex_extractor extract --pdf-dir corpus-main --html-dir "Claude outputs/corpus/html" --out regex_output

# 2) Draw the blind, stratified gold-standard sample
python -m regex_extractor sample --run regex_output --n 200 --seed 42

# Debug a single file or sentence
python -m regex_extractor test --file corpus-main/2008.11693v1.pdf
python -m regex_extractor test --text "A peak zT of 2.6 at 923 K in SnSe."
```

## Outputs (`regex_output/`)

| File | Content |
|---|---|
| `paragraphs.jsonl` | every paragraph (paper, source, kind, text, hit count, relevant flag) |
| `candidates.jsonl` / `.csv` | one row per (material, property, value, T) candidate |
| `summary.json` | counts per source, plus HTML-vs-PDF counts for papers that have both |
| `errors.jsonl` | files that could not be read |
| `gold_sample/gold_annotation_sheet.csv` | **blind** sheet: paragraph text + empty schema columns |
| `gold_sample/sample_key.jsonl` | stratum, inclusion probability, weight and regex output per sample (do not show the annotator) |
| `gold_sample/sampling_report.json` | design, scope, stratum populations and sample sizes |

## Schema and canonical units (`schema.py`)

`material` · `ZT` (–) · `T_K` (K) · `S_uVK` (μV K⁻¹, signed) · `kappa` (W m⁻¹ K⁻¹) ·
`sigma` (S m⁻¹) · `PF` (μW cm⁻¹ K⁻²) · `doping` (text, or cm⁻³ for carrier concentration).
All extractors of the project should emit these units.

## How it works

* Unit-anchored: S, κ, σ, ρ (→ σ = 1/ρ), PF, carrier concentration. The unit decides the property.
* Keyword-anchored: ZT (`ZT`, `zT`, `ZT_max`, `figure of merit`); guards against
  `ZT at 300 K`, `Figure 7`, `ZT = S²σT/κ`.
* Doping: `Na-doped`, `doped with Na`, `2 at.%`, `x = 0.02` (only in doping context), cm⁻³.
* Context: temperature (forward, then backward in the sentence; "room temperature" → 300 K, flagged),
  κ sub-type (lattice / electronic / bipolar), nearest chemical formula in the sentence.
* Suspicious hits are **flagged, not dropped**: `out_of_range`, `derived_from_resistivity`,
  `computational_context`, `citation_in_sentence`, `room_temperature_as_300K`,
  `unit_exponent_missing`, `pdf_flattened_exponent_guess`, `ambiguous_flattened_exponent`,
  `no_material_found`.
* PDF reading: some PDFs (typically Word-generated author manuscripts) give one text block per
  **line**. Blocks are merged into paragraphs when they continue each other (same column,
  similar font size, small vertical gap, and the previous text does not end a sentence or the
  next starts in lower case; mid-sentence breaks across columns/pages are joined too).
  `paragraphs.jsonl` records `n_blocks` per PDF paragraph.
* Unicode superscripts are kept as exponents before NFKC: `10⁵ S m⁻¹` → `10^5 S m^-1`.
* Flattened PDF exponents (`10-4`, `1017`): the exponent reading replaces the literal one
  only if the literal value is implausible and the exponent value is plausible, both checked
  in the output unit (after ρ → σ). If both are plausible, the literal value is kept and
  the other reading goes to `value_alt`.

## Sampling design

**Scope rule** (`extractor.SCOPE_RULE`, `extractor.in_scope`): a paragraph is *in scope* if it
contains a thermoelectric keyword (`RELEVANCE_RE`) **and** at least one digit. The rule is
applied to every paragraph before stratification, so the scope boundary is also a stratum
boundary. A paragraph with regex hits but no keyword is out of scope, like any other.

| Stratum | Content | Default share (n = 200) |
|---|---|---|
| `ZT`, `S_uVK`, `PF`, `kappa`, `sigma`, `doping` | in scope, regex hit (highest-priority property) | remaining 120, proportional, min 15 |
| `in_scope_no_hit` | in scope, no regex hit | 20 % = 40 (`--none-frac`) |
| `out_of_scope` | every paragraph failing the rule, with or without hits (control) | 20 % = 40 (`--control-frac`) |

Reporting:

* **In-scope precision/recall** use in-scope units only, and every method's output is
  filtered with the same `in_scope()` rule before scoring.
* **Control stratum** is reported separately: number of gold records found outside the
  scope. With 40 control paragraphs and zero records found, the share of out-of-scope
  paragraphs holding a record is below 7.2 % (95 %, exact binomial bound
  `1 - 0.05^(1/n)`; the report also gives it as a paragraph count).
* **Budget:** the sample never exceeds `--n`. Every non-empty stratum gets at least one
  paragraph (so no paragraph has zero inclusion probability); if `--n` is smaller than the
  number of non-empty strata the command stops with an error. The `min-per-stratum` floor
  is scaled down so it never eats into the fixed shares. If the hit strata are exhausted
  (small corpus), the unused budget goes to the strata with the most room.
* Default (`--max-per-paper 0`): stratified simple random sampling; weights `N_h / n_h` are
  exact.
* `--max-per-paper k` caps paragraphs of one paper **within each stratum**, so quota used
  in one stratum never blocks another. Inclusion probabilities are then estimated by Monte
  Carlo (`--mc-reps`, the realized draw counted as one replication, so no sampled unit gets
  `pi = 0`). The report lists `population_units_never_drawn_in_mc` (should be 0; if not,
  raise `--mc-reps`) and any stratum the cap left below its allocation.
* Use the per-sample `weight` for weighted estimates and a **paper-level bootstrap** for
  confidence intervals (paragraphs of one paper are correlated).

## Annotating the gold sheet

One row per paragraph is given. If a paragraph holds several records (e.g. two materials
or two temperatures), copy the row and keep the same `sample_id`. Leave a field empty if
the paragraph does not state it. Annotate what the paragraph *reports*; values quoted
from other work get `notes = cited`.

## Known limitations (write them down in the paper)

* Material names without a formula (e.g. "half-Heusler", "skutterudite") are not detected.
* Values only in tables or figures are not captured (captions are).
* Material/temperature linking is proximity-based; multi-value sentences can mis-pair.
* PDF text loses superscripts; `10-4` and `1017` are re-interpreted only when the
  literal reading is physically implausible (flagged).

## Benchmark adapter (method M0)

The shared schema moved to `evaluation/schema.py` (the method-independent
contract); `schema.py` here only re-exports it, so existing imports still work.
The extraction rules (`extractor.py`) are frozen; their hash is recorded in
`evaluation/manifests/regex_frozen_2026-10-09.json`.

```bash
# from the arxiv folder
python -m regex_extractor.predict --split dev     # development runs
python -m regex_extractor.predict --split test    # once, after all methods are frozen
```

Writes `results/regex/<run_id>/` (`predictions.jsonl`, `paragraph_status.jsonl`,
`run.json`); `run.json` states whether the rules still match the frozen hash.
Only the paragraph text of `evaluation/data/<split>/inputs.jsonl` is used.

M0 is a **corpus-informed baseline**: its rules were developed on the full
corpus before the dev/test split, so its test scores are not scores on unseen
data (see `evaluation/PROTOCOL.md` §3).
