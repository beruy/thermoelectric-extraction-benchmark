# Evaluation protocol — thermoelectric data extraction methods

Status: **v1.1 (2026-10-20) — frozen; changes after v1.0 in §13.** No open item remains. Methods and
scorer are frozen in `evaluation/manifests/methods_frozen_2026-10-19.json`. After freezing, every change gets a dated entry in the change log
(§13) and is reported in the paper.

## 0. Decisions and open items

| Item | Status | Value |
|---|---|---|
| Dev/test split | decided | paper level, 30 % dev / 70 % test, seed 20261009; all files/versions of a paper in one split |
| Sample sizes | decided | dev 100, test 200 paragraphs (initial evaluation) |
| Value tolerance | decided | relative 1 % after unit conversion; exact match if the gold value is 0; sign kept |
| Material matching (primary) | decided | safe formatting normalization only (§6.3) |
| Material matching (secondary) | decided | stoichiometry-aware, sensitivity analysis only |
| Temperature tolerance | decided 2026-10-19 | ±1 K after °C → K conversion (§7.2) |
| Room-temperature rule | decided 2026-10-19 | primary: empty or 293–300 K; sensitivity: empty only (§7.2) |
| Second annotator | decided 2026-10-20 | none; inter-annotator reliability is not measured and is reported as a limitation (§5.3) |
| Licences | decided 2026-10-20 | §11 |

## 1. Question and methods

Question: how accurately do different extraction approaches recover
thermoelectric property records from the scientific literature, at what cost?

| ID | Name in the paper | Components | Folder |
|---|---|---|---|
| M0 | Regex baseline (corpus-informed) | rules only | `regex_extractor/` |
| M1 | ChemDataExtractor thermoelectric parsers | CDE 2.0 + published thermoelectricsdb parsers (Sierepeklis & Cole 2022) + our schema mapping | `chem_data_extractor/` |
| M2 | MaterialsBERT-based PolymerNER + rule-based linking | `pranav-s/PolymerNER` (no retraining) + linking rules + property-name dictionary | `materialsbert_extractor/` |
| M3 | Claude, single prompt | one API call per paragraph, fixed prompt | `claude_data_extractor/` |
| M4 | Claude agent | `pdf-extractor` Claude Code subagent on paragraph batches, evidence quotes, read-back check | `agent_extractor/` |

* The LLM methods M3 and M4 receive the same task definition,
  `evaluation/task_spec.md`: properties, canonical units and the annotation
  rules of §5.2, without examples from the samples. It is part of the
  protocol version; M0–M2 encode the task in their own rules and mappings.
* Hybrid methods are legitimate if every component is named. To measure the
  contributions of CDE, BERT and LLM separately, M1 has no LLM step and M2 has
  no LLM fallback.
* Claims are limited to the configuration tested. M2 is a polymer-trained NER
  model transferred to thermoelectrics; a weak M2 result is not a result about
  MaterialsBERT approaches in general.
* Using the published M1 parsers does not by itself make M1 neutral:
  pre-processing, record cleaning and our schema mapping also affect its score
  and are documented. Published success rates of M1 do not replace our test.

## 2. Unit of analysis and input

* Unit: one paragraph as produced by `regex_extractor/readers.py`
  (`READER_VERSION = 2`), from one source per paper (HTML when available, else
  PDF). Reader v2 merges PDF line blocks into paragraphs by layout (short last
  line, indentation) and sentence cues, drops page numbers, continues a
  paragraph across a figure or caption, and stops at a reference list with or
  without a heading. The frame is built in Google Colab (Python 3.13.16,
  PyMuPDF 1.28.2) with `--pdf-backend pymupdf`, so a missing PDF library stops
  the run instead of silently switching backend.
* Method input (`evaluation/data/<split>/inputs.jsonl`): `sample_id`,
  `paper_id`, `para_id`, `text`. Extraction may use only `text`. No other part
  of the paper, no metadata, no strata, no other method's output.
* Gold labels and sampling keys are kept apart from method inputs
  (`annotation/`, `gold/`, `private/`) and are read only by the scorer.
* Text the reader does not produce (table cells, text lost in PDF parsing,
  references) is outside the corpus for every method. Full-PDF extraction is a
  separate experiment (§10), never pooled with the paragraph benchmark.

## 3. Corpus, split and leakage

* Population: the 311 papers of `corpus-main` (+ their HTML versions).
* Split by paper before sampling (`evaluation/sample.py`): versions of one
  arXiv paper and a DOI file belonging to an arXiv paper share one group. Groups
  are shuffled with seed 20261009; 30 % dev, 70 % test. Result: 93 dev groups,
  218 test groups (`evaluation/data/split.json`).
* dev: used to develop and tune every method. test: not inspected by anyone
  developing a method until all methods are frozen (§9). The annotator must
  read test paragraphs to label them; this is allowed, but the annotator does
  not see any method output on test before scoring. Roles and the rule for an
  annotator who also develops methods: §5.4.

### Known leakage — must be reported

* Frame v2 (2026-10-13, `evaluation/manifests/regex_frozen_2026-10-13.json`)
  replaces frame v1. The v1 frame had been produced by an older reader than the
  one hashed in the 2026-10-09 manifest and split most PDF paragraphs into
  fragments (42 of 57 sampled dev PDF paragraphs under 150 characters; 12 of 62
  in v2). Reader v2 was developed on dev papers only. The paper-level split and
  all seeds are unchanged; the samples were redrawn from the new frame. The v1
  samples were never scored; their annotation files were deleted and the rest
  archived in `evaluation/archive/frame_v1_2026-10-09/`.
* M0's rules were developed on the full corpus before the split. Freezing them
  now (hashes in `evaluation/manifests/regex_frozen_2026-10-09.json`) prevents
  further leakage but does not remove the past one. The re-drawn test set is
  **not unseen data for M0**. M0 is reported as a *corpus-informed baseline*.
* Any method that uses M0's code or rules inherits this limitation; such
  dependencies are documented per method. M4 no longer reads `regex_extractor`
  (scope rule and flag names removed on 2026-10-14); it reads only the task
  definition and its input batch.
* A claim of performance on genuinely unseen data needs an additional test set
  of papers not used in any development (e.g. collected after the freeze).
* Moving methods into separate folders organizes development; it does not
  remove this leakage.

## 4. Sampling

* The stratified design of `regex_extractor/sampling.py` is applied separately
  within each split (`evaluation/sample.py`): strata `ZT`, `S_uVK`, `PF`,
  `kappa`, `sigma`, `doping` (in scope, M0 hit), `in_scope_no_hit`,
  `out_of_scope` (control). Paragraphs without data are therefore in the sample.
* Strata are defined by M0 hits. This stratifies on M0 but does not select on
  it: every paragraph has a known non-zero inclusion probability, and the paper
  states how the strata were formed.
* Sizes: dev 100 (seed 1009), test 200 (seed 2009). Sample ids `D0001…`,
  `T0001…`.
* The pre-split sample (2026-10-04, not annotated) is archived in
  `evaluation/archive/pre_split_gold_sample_2026-10-04/` and not used.
* Reporting: the number of gold records per property is reported with every
  score, with confidence intervals. Because strata are sampled at different
  rates, two kinds of numbers are reported and always labelled:
  * **sample-level** (unweighted): describes exactly the annotated paragraphs;
  * **corpus-level** (weighted by 1/π): estimates the in-scope paragraphs of
    the split's papers.

## 5. Gold standard

### 5.1 Workflow and record format

The annotator fills `evaluation/data/<split>/annotation/annotation_sheet.csv`
(one prefilled row per paragraph; copy a row for each further record, same
`sample_id`, next `record_no`) and saves it as
`evaluation/data/<split>/gold/gold_records.csv`. The `text` column is ignored
by the scorer. Every paragraph needs at least one row; a paragraph without a
record gets `property = NONE`.

| Field | Content |
|---|---|
| `sample_id`, `record_no` | paragraph id; 1, 2, … |
| `material` | material as named in the paragraph for this value |
| `property` | `ZT`, `S_uVK`, `kappa`, `sigma`, `PF`, `doping`, or `NONE` |
| `value` | number in canonical unit (§6.1); empty for text-only doping |
| `value_max` | upper bound of a reported range |
| `value_as_written`, `unit_as_written` | exact text |
| `T_K` | temperature in K if stated as a number for this value |
| `T_as_written` | e.g. `923 K`, `room temperature`, `T < 50 K` |
| `kappa_type` | `total`, `lattice`, `electronic`, `bipolar`, `unspecified` |
| `qualifier` | `max`, `min`, `avg`, `range` |
| `origin` | `reported` or `cited` |
| `context` | `experimental` or `computational` |
| `doping_text`, `carrier_conc_cm3` | doping only |
| `material_aliases` | `;`-separated names also accepted for this record |
| `notes` | free text |

### 5.2 Annotation rules

* Annotate what the paragraph states. Values from other work: `origin = cited`.
* One record per (material, property, value, temperature, condition); repeats
  of the same value in one paragraph are one record.
* Ranges: lower bound in `value`, upper in `value_max`, `qualifier = range`.
  `x ± e`: `value = x`.
* "Room temperature" and bounds such as "below 50 K": `T_K` empty, text kept
  in `T_as_written`.
* Do not compute values the paragraph does not state. Exceptions: conversion to
  the canonical unit, the `×10` notation below, and σ = 1/ρ for resistivity.
* Approximate values (`~`, `≈`, "about", "around", "in the order of (about)")
  with an explicit unit are recorded as stated, without a qualifier.
* Values stated only as an inequality or bound (`>`, `<`, `≥`, "at least",
  "above", "exceeding") are not recorded; the bound is mentioned in `notes`.
  A bound is not a value, and recording it as one would reward a method that
  misreads it.
* Numbers visibly corrupted by PDF parsing (lost superscripts such as
  `1019` for 10^19, merged digits) are not recorded and are not repaired; the
  problem is noted in `notes`. The number of paragraphs affected is reported as
  a reading loss, the same for every method. Exception: a number written with an
  explicit `×10` (or `x10`) prefix is not ambiguous and is recorded with the
  exponent restored: `1.3 × 10-2` = 0.013, `2.69×1019` = 2.69 × 10^19. A bare
  `1019` or `~103` stays excluded.
* Table text: a paragraph that is a table flattened by the reader (rows of
  numbers with column headers) gets `NONE`, consistent with §2 (tables are out
  of scope). One table would otherwise outweigh the rest of the sample.
* Dataset statistics (mean, median, histogram peak over many materials) are not
  property values of a material and are not recorded.
* A carrier concentration that is the condition of other values is one `doping`
  record per (material, concentration, carrier type), however often it is
  repeated in the paragraph.
* A carrier concentration given only as a range ("between 10^17 and 10^18
  cm^-3") is not recorded: `carrier_conc_cm3` is single-valued, so the record
  could not be matched by any method. It is noted in `notes`.
* Derived quantities with a property's name are not that property: e.g. the
  effective active-cooling conductivity κ_eff = κ + PF·T_H²/(2ΔT) is not κ.
* `material` is written as in the paragraph, even with source markup; other
  names of the same material go in `material_aliases`, which need not appear
  in the text. A composition variable is not substituted (`NixAu1-x` for
  x = 0.1); the substituted formula may be given as an alias.
* An LLM may pre-annotate dev paragraphs; every such row says so in `notes`
  and is reviewed by the annotator. The test paragraphs were planned without
  pre-annotation (§5.4); in the event they were pre-annotated by GPT-6 Astra
  (OpenAI, not a Claude model) and every record was reviewed and corrected by
  the annotator. Every test row says so in `notes` (deviation, §5.4, §13).
* A Seebeck coefficient given as an absolute value is recorded with its sign
  when the same paragraph states the sign explicitly (e.g. "n-type with
  S < 0", "negative Seebeck coefficient"); noted in `notes`.
* Resistivity → `sigma` only when its unit is explicit (σ = 1/ρ), noted in
  `notes`.

### 5.3 Reliability

* Decided 2026-10-20: the gold standard has **one annotator**. No second
  annotator is used, so inter-annotator reliability is not measured. The paper
  reports this as a limitation, together with what reduces annotator error:
  the written rules (§5.1–5.2), the double-check of every record against the
  paragraph text, and the dev resistivity audit (gold v1.1).
* The pre-selected subset (`test/private/reliability_subset.json`, 40
  paragraphs, seed 3009) is kept. If the annotator later re-labels it blind
  (≥ 2 weeks after the first pass), the result is reported as
  **intra-annotator consistency**, whatever it is, and not as inter-annotator
  reliability.

### 5.4 Annotator and developer roles

* The annotator of the gold standard also takes part in method development
  (prompts, linking rules, adapters on dev). To prevent leakage from test
  annotation into methods, test paragraphs are annotated only after all methods
  and this protocol are frozen (§9, steps 2–3).
* If any test annotation happens before that point, its date and extent are
  recorded in the change log (§13) and reported as a limitation in the paper.
* Test paragraphs and test gold labels are never used to change a method, a
  prompt, a dictionary or a scoring rule.
* Deviation (2026-10-20): the test gold was pre-annotated by GPT-6 Astra and
  reviewed by the annotator, after all methods were frozen and before any
  method was run on test. Because the draft came from a language model, the
  gold may favour language-model methods (M3, M4) over M0–M2; this is reported
  as a limitation. The draft model is not from the family evaluated (Claude).
* AI-assisted development sessions (e.g. Claude Code) do not open files under
  `evaluation/data/test/` during development. The single test run of a frozen
  method (§9, step 4) is exempt.

## 6. Normalization

### 6.1 Canonical units (`evaluation/schema.py`)

ZT dimensionless · S µV K⁻¹ (signed) · κ W m⁻¹ K⁻¹ · σ S m⁻¹ ·
PF µW cm⁻¹ K⁻² · T K · carrier concentration cm⁻³. Each method converts units
itself; the scorer does not repair a method's units.

### 6.2 Property names

Fixed mapping to the five core properties plus doping. Thermopower = S only
with V K⁻¹-type units. Thermal diffusivity is not κ; conductance is not σ.

### 6.3 Material strings

* **Primary:** safe formatting normalization only — Unicode NFKC (subscript
  digits → digits), removal of whitespace and markup characters `_ { } $`.
  Letter case (element symbols), dopant amounts, variable compositions and
  sample labels are kept. A match is an equal normalized string or a gold
  alias.
* **Secondary (sensitivity only):** stoichiometry-aware comparison of plain
  formulas (same elements, fractions within 0.01). Never in the primary score.

### 6.4 Diagnostics (not scored)

Unmatched predictions whose value matches a gold value after a factor
10^±2, 10^±4, 10^±6 → unit error; S matching only after a sign flip → sign
error.

## 7. Scoring (`evaluation/score.py`)

### 7.1 Matching

Within one paragraph and one property, one-to-one maximum bipartite matching
between predicted and gold records, computed separately for each level.
Exact duplicates in a method's output are collapsed first; their number is
reported.

### 7.2 Criteria

* **value:** relative 1 % after unit conversion; exact if gold is 0; sign must
  agree; ranges need both bounds. *(decided)*
* **temperature:** *(decided 2026-10-19)*. The tolerance covers small
  differences from reading and unit conversion, not measurement uncertainty.
  * Gold gives a numeric temperature: |ΔT| ≤ 1 K after °C → K conversion; an
    empty prediction does not match (a text saying "295 K" needs a temperature).
  * Gold says explicitly "room temperature" (`T_K` empty, `T_as_written`
    keeps the wording): an empty prediction or one in 293–300 K (bounds
    included) matches. Reason: methods that do not read `task_spec.md` write
    room temperature as a number by their own convention (e.g. M1's published
    pipeline uses 295 K); the rule separates notation from reading errors.
  * Gold gives no temperature: only an empty prediction matches.
  * Gold gives only a bound ("below 50 K"): `T_K` empty, the bound kept in
    `T_as_written` or `notes`; only an empty prediction matches.
  * Sensitivity analysis (`--rt-strict` in `score.py` and `compare.py`): the
    room-temperature case accepts only an empty prediction; nothing else
    changes. Both are reported.
  * Decided before the effect on any method's score was computed.
* **material:** §6.3 primary.
* **kappa_type:** `lattice`, `electronic`, `bipolar` must agree; `total`,
  `unspecified` and empty are treated as one class.
* **doping (extended):** carrier concentration within 5 % if gold gives one,
  else the same set of element symbols in the dopant text.

### 7.3 Levels

L1 property + value · L2 + temperature · **L3 + material (primary)**.

### 7.4 Field sets

* **Core (primary):** ZT, S, κ, σ, PF. Temperature is an attribute, never a
  sixth property.
* **Extended:** doping, separate table.
* `origin` and `context`: attribute accuracy on L3 matches (secondary).

### 7.5 Unsupported fields

Every run declares its `capabilities`. Reported for every method:
**core_all** (unsupported properties count as misses) and
**core_supported_only**. Unsupported fields appear as "not supported", never
disappear from tables. Known: M1 has no doping.

### 7.6 Estimation

Precision, recall, F1 per level and field set, sample-level and corpus-level
(Hájek ratio with weights 1/π). In-scope paragraphs only; the control stratum
is reported separately. 95 % CIs by paper-level bootstrap (B = 2000, seed 7);
paired method differences use the same resamples.

### 7.7 Failures

Per-paragraph status (`paragraph_status.jsonl`: ok / error / timeout). A failed
paragraph is distinct from a valid empty extraction: its predictions are
ignored and all its gold records count as misses; the number of failed
paragraphs is reported.

## 8. Method contract and folder layout

```
evaluation/   PROTOCOL.md  schema.py  sample.py  score.py  tests/  manifests/  archive/
              data/<split>/inputs.jsonl  annotation/  gold/  private/
regex_extractor/  chem_data_extractor/  materialsbert_extractor/
claude_data_extractor/  agent_extractor/
results/<method>/<run_id>/  predictions.jsonl  paragraph_status.jsonl  run.json  scores/
```

* Every method folder has its own README, dependency file, configuration and
  command-line entry point; incompatible dependencies use separate Python
  environments (expected for CDE).
* Methods do not read each other's outputs. Any dependency of one method on
  another method's code or rules is documented (§3).
* Output records follow `evaluation/schema.py: PREDICTION_FIELDS` in canonical
  units; unknown = null.
* `run.json` (`RUN_META_FIELDS`): method and code version, model and
  parameters, input file hash, times, paragraph/failure counts, calls, tokens,
  cost with price table, hardware, capabilities. Unmeasurable fields are null.
* Run folders and score files are never overwritten.

## 9. Development, freezing, single test run

1. Develop and tune on dev only.
2. Freeze each method: code version/commit, prompt text, dictionaries, model
   ids, together with sample ids and file hashes
   (`evaluation/data/manifest.json`).
3. Freeze this protocol (version tag), then annotate the test sample (§5.4).
   "Freezing" fixes the rules used for test scoring; it does not lock the
   file. Later changes are dated in §13 and reported.
4. Run every frozen method once on test.
5. Score. No method changes after test scores are seen; later changes are new,
   separately reported runs.

## 10. Secondary experiments

* Agent: same paragraph input as all methods, in batches of 10 per agent
  context (told to treat paragraphs independently); invocations, tokens and
  cost reported when the session provides them. M3 vs M4 (same model) separates single prompt from agent;
  ablations switch off one agent component at a time (attribution/vocabulary
  rules, evidence requirement, read-back check).
* Full-PDF extraction (whole papers incl. tables, with its own gold): not part
  of this study (decided 2026-10-20); named as future work.
* HTML vs PDF reading loss from `regex_output/summary.json`.

## 11. Licences — checked before any code is adapted

| Component | Terms | Status |
|---|---|---|
| ChemDataExtractor-TE 2.0.0-te (M1) | MIT (package LICENSE) | checked 2026-10-17; used unmodified from the published tarball |
| thermoelectricsdb (M1 parsers and cleaning, commit 78e5003) | MIT (repository LICENSE) | checked 2026-10-17; cited (Sierepeklis & Cole 2022) |
| `pranav-s/PolymerNER` (M2 model, revision 4f7bb8b) | model card licence tag "other", no terms on the card; the authors' repository states academic, non-commercial use | used unchanged for academic, non-commercial research; cited (Shetty et al. 2023) |
| Ramprasad-Group/polymer_information_extraction (M2 linking code, commit d08f2d3) | Georgia Tech Research Corporation licence: academic, non-commercial; copies keep the notices; modified files marked | checked 2026-10-19; vendored in `materialsbert_extractor/vendor/` with LICENSE and NOTICE |
| chemdataextractor 1.3.0 (used by the M2 linking code) | MIT | checked 2026-10-19 |
| PromptDataExtraction | academic, non-commercial use stated | closed 2026-10-20: not used, no code copied; cited as related work only |
| Anthropic API and Claude Code (M3, M4) | provider terms accepted for the account (API key; Claude Pro subscription) | closed 2026-10-20: used as a service to extract data for evaluation; outputs are not used to train any model; model identifiers and versions reported |

No code is copied from a component whose row is open.

## 12. Files that define this evaluation

| File | Role |
|---|---|
| `evaluation/manifests/regex_frozen_2026-10-09.json` | M0 code and frame v1 hashes before the split (superseded frame) |
| `evaluation/manifests/regex_frozen_2026-10-13.json` | M0 code with reader v2, frame v2 hashes, build environment |
| `evaluation/data/split.json` | paper → split, seed, frame hashes |
| `evaluation/data/manifest.json` | sampling parameters, sample sizes, hashes of all sample files |
| `evaluation/manifests/dev_gold_v1_2026-10-14.json` | dev gold v1 (kept as `gold_records_v1.csv`) |
| `evaluation/manifests/dev_gold_v1_1_2026-10-19.json` | dev gold v1.1 (current `gold_records.csv`); resistivity audit |

## 13. Change log

| Date | Change | Reason |
|---|---|---|
| 2026-10-09 | v0.1 draft | — |
| 2026-10-09 | v0.2: decisions on split, sizes, value tolerance, material matching, reliability; leakage wording; S code `S_uVK`; folder layout; split and samples drawn | review of v0.1 |
| 2026-10-12 | v0.3: annotator may read test paragraphs, never method output (§3); annotator/developer roles and test-annotation timing (§5.4); protocol freeze placed before test annotation, steps renumbered (§9); inequalities, bounds and PDF-corrupted numbers are not recorded (§5.2) | annotator also develops methods; review of "test not inspected" wording |
| 2026-10-13 | v0.4: PDF reader v2 and frame v2 (§2, §3); same split and seeds, samples redrawn; v1 annotation files deleted, v1 data archived; M0 rules unchanged | v1 frame built by an older reader; most PDF paragraphs were fragments |
| 2026-10-14 | v0.5: §5.2 rules for ×10 notation, table text, dataset statistics, repeated doping conditions, carrier-concentration ranges, derived quantities, material names/aliases, LLM pre-annotation on dev only | decisions while reviewing the ChatGPT-pre-annotated dev sheet |
| 2026-10-14 | Dev gold v1 frozen (`evaluation/manifests/dev_gold_v1_2026-10-14.json`, 135 records); LLM pre-annotation and Claude corrections recorded per row; approved by the annotator; frozen before any method was scored | — |
| 2026-10-14 | §1, §3, §10: shared task definition `evaluation/task_spec.md` for M3/M4; M4 adapted to the contract (`agent_extractor/run.py`), M0 dependency removed, PDF mode dropped from the M4 definition | M4 open issues resolved |
| 2026-10-14 | M3 implemented (`claude_data_extractor/predict.py`): one call per paragraph, system prompt = `evaluation/task_spec.md`, structured JSON output, default model `claude-opus-5-5`, temperature not set (adaptive thinking always on); responses cached per paragraph | M3 adapter |
| 2026-10-15 | `evaluation/compare.py`: side-by-side comparison of runs with paired paper-level bootstrap CIs of F1 differences; `evaluation/diagnose.py` pairs records L3-first | method comparison on dev |
| 2026-10-16 | M4 dev run (`results/agent/dev_20261013T232821Z`): Claude Code 2.1.296, Opus 5.5, Pro subscription; batch_002 run twice and overwritten by the agent (identical records; first output kept in `notes/`) | run notes |
| 2026-10-17 | M1 implemented (`chem_data_extractor/predict.py`): published ChemDataExtractor-TE `te_parse`, authors' cleaning, our mapping to the contract; Python 3.8, pandas < 2 | M1 adapter |
| 2026-10-19 | M2 implemented (`materialsbert_extractor/predict.py`): PolymerNER + vendored record linking (`polymer_filter=False`), our unit-exponent normalisation, sentence chunking ≤ 510 word pieces, property-name dictionary and unit conversion; own environment | M2 adapter |
| 2026-10-19 | v0.6: §5.2 approximate values recorded; unit conversion, `×10` and σ = 1/ρ named as exceptions to "do not compute"; §11 licences of M1/M2 components checked | clarifications found during the resistivity audit; licences before code use |
| 2026-10-19 | Dev gold v1.1 (`evaluation/manifests/dev_gold_v1_1_2026-10-19.json`, 140 records): resistivity audit of 24 dev paragraphs by the annotator; 22 agree with v1, D0066 and D0076 changed from NONE to σ records; both are paragraphs whose method outputs had been seen; scores reported against v1 and v1.1 | v1 contradicted §5.2 for resistivity |
| 2026-10-19 | §0, §7.2: temperature tolerance ±1 K and room-temperature rule decided (primary lenient, strict as sensitivity); `score.py` `T_TOL_STATUS = decided`, `--rt-strict`; decided before computing score effects | open item closed before test annotation |
| 2026-10-19 | Methods and scorer frozen (`evaluation/manifests/methods_frozen_2026-10-19.json`, `evaluation/freeze.py`): file hashes of M0–M4 and the scorer, external components, Python environment freezes of M1/M2 (`evaluation/manifests/env/`); final M2 dev run `results/bert/dev_20261019T215941Z` (60 predictions, current code incl. the sentence-end `K^{2}` fix); M1 re-run in the rebuilt environment (`results/cde/dev_20261019T220217Z`) gives byte-identical predictions to `dev_20261016T230248Z`; every test run is preceded by `python -m evaluation.freeze check`; edits to this protocol after the freeze are documentation and do not invalidate the frozen methods | §9 freeze before test annotation |
| 2026-10-20 | v1.0, protocol frozen: second annotator decided as none (§5.3, reported as a limitation; optional later intra-annotator re-labelling reported if done); §11 PromptDataExtraction closed as unused, Anthropic API/Claude Code row closed | last open items closed before test annotation |
| 2026-10-20 | v1.1: test gold v1 (`evaluation/manifests/test_gold_v1_2026-10-20.json`, 346 records in 200 paragraphs); deviation from §5.4: pre-annotated by GPT-6 Astra (OpenAI) and reviewed by the annotator, written in every row's `notes` and reported as a limitation; §5.2 sign rule for S given as an absolute value with the sign stated in the paragraph (2 records); §10 full-PDF experiment removed from this study (future work). Methods unchanged (frozen 2026-10-19) | test annotation completed |
| 2026-10-21 | Single test run of all five frozen methods and scoring; events and deviations (M0 re-executed, identical; M3 resumed after API credit ran out, cached answers unchanged; M4 run with Claude Code 2.1.302 instead of 2.1.296, batch_008 run last) in `results/test_run_notes_2026-10-20.md`; comparisons `results/comparisons/test_20261020T225711Z` (primary) and `…T225731Z` (strict room temperature) | §9 step 4 |
| 2026-10-21 | A complete earlier M3 test run (`results/claude/test_20261020T152747Z`) was found; rule recorded before scoring it: the first complete run of each method is primary (as for M0). M3 primary = `test_20261020T152747Z`; `test_20261020T153852Z` reported as a replicate. Comparisons `results/comparisons/test_20261021T000520Z` (primary), `…T000544Z` (strict room temperature), `…T000608Z` (corrected gold v1.1), `…T000614Z` (M3 replicate). Test gold v1.1 (corrected): private-use characters removed from 4 material strings, sensitivity only | release preparation |
