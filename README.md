# Benchmarking thermoelectric property extraction from scientific text

Code, protocol, gold standards and all method outputs for the paper of the same
title, preprint on ChemRxiv:
[10.26434/chemrxiv.15010913/v1](https://doi.org/10.26434/chemrxiv.15010913/v1).

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23522991.svg)](https://doi.org/10.5281/zenodo.23522991)

Five methods extract thermoelectric property records (ZT, Seebeck coefficient,
thermal and electrical conductivity, power factor; doping separately) from
single paragraphs of 311 papers (299 arXiv preprints, 12 open-access
journal articles). The methods were frozen before the test
sample was annotated. A record is correct at the primary level (L3) only if
property, value, temperature and material all match the gold standard.

## Test results (200 paragraphs, core properties, sample-level F1)

| Method | L1 value | L2 + temperature | L3 + material (95 % CI) |
|---|---|---|---|
| M3 Claude, single prompt | 0.973 | 0.948 | **0.792** (0.71–0.87) |
| M4 Claude agent | 0.969 | 0.943 | 0.734 (0.64–0.83) |
| M0 regular expressions | 0.688 | 0.573 | 0.221 (0.16–0.29) |
| M1 ChemDataExtractor-TE | 0.108 | 0.100 | 0.062 (0.03–0.11) |
| M2 PolymerNER + rule-based linking | 0.595 | 0.200 | 0.059 (0.03–0.09) |

Corpus-level estimates, paired differences and sensitivity analyses are in
`results/comparisons/` (primary: `test_20261021T000520Z.md`).

## Layout

| Path | Content |
|---|---|
| `evaluation/` | protocol (`PROTOCOL.md`), task definition, scorer, tests, manifests |
| `evaluation/data/` | dev and test inputs, annotation sheets, gold standards, sampling keys |
| `regex_extractor/` … `agent_extractor/` | methods M0–M4, each with its own README |
| `results/` | predictions, scores and run notes of every run |

## Reproducing the scores

Scoring needs only Python 3 and its standard library (tested with 3.13):

```bash
python -m evaluation.score --split test --run results/claude/test_20261020T152747Z
python -m evaluation.compare --split test \
    --run results/agent/test_20261020T181227Z --run results/claude/test_20261020T152747Z \
    --run results/regex/test_20261020T152543Z --run results/cde/test_20261020T181703Z \
    --run results/bert/test_20261020T181141Z
python -m evaluation.freeze check --manifest evaluation/manifests/methods_frozen_2026-10-19.json
python -m unittest discover evaluation/tests
```

Re-running the methods is described in each method's README (M1 and M2 need
Python 3.8 environments, listed in `evaluation/manifests/env/`; M3 needs
`ANTHROPIC_API_KEY`; M4 needs Claude Code). LLM outputs are not deterministic.

## Corpus and limitations

The papers are identified by arXiv identifiers or DOIs in
`evaluation/data/split.json`;
the papers and the full paragraph frame are not redistributed. Main
limitations, with all deviations listed in `evaluation/PROTOCOL.md` §13 and
`results/test_run_notes_2026-10-20.md`:

* **Single annotator:** the gold standards were pre-drafted by OpenAI models
  and checked record by record by one annotator; inter-annotator agreement was
  not measured.
* **M0 leakage:** the regular expressions were written on the full corpus
  before the split, so the test papers are not unseen for M0.

## Licences

Code: MIT (`LICENSE`), except the vendored third-party code in
`materialsbert_extractor/vendor/`, which keeps its own licence. Data and
results: CC BY 4.0 (`LICENSE-DATA`); paragraph texts remain under the
licences of the source papers.

## Citation

Please cite the preprint:

> Uyanık, B. (2026). Benchmarking thermoelectric property extraction from
> scientific text. ChemRxiv.
> https://doi.org/10.26434/chemrxiv.15010913/v1

Release v1.0 of this repository is archived on Zenodo:
[10.5281/zenodo.23522991](https://doi.org/10.5281/zenodo.23522991).
See also `CITATION.cff`.
