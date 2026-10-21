# Test runs, 2026-10-20/21 — run notes

All five methods were run once on the 200 test paragraphs after the methods
were frozen (`evaluation/manifests/methods_frozen_2026-10-19.json`) and the test
gold was written (`evaluation/manifests/test_gold_v1_2026-10-20.json`).
`python -m evaluation.freeze check` gave `FROZEN STATE OK` before the runs and
again before scoring.

| Method | Run used for scoring | Predictions | Failed paragraphs |
|---|---|---|---|
| M0 regex | `results/regex/test_20261020T152543Z` | 302 | 0 |
| M1 ChemDataExtractor-TE | `results/cde/test_20261020T181703Z` | 19 | 0 |
| M2 PolymerNER + linking | `results/bert/test_20261020T181141Z` | 132 | 0 |
| M3 Claude, single prompt | `results/claude/test_20261020T153852Z` | 309 | 0 |
| M4 Claude agent | `results/agent/test_20261020T181227Z` | 292 | 0 |

## Events and deviations

* **M0 run twice.** The notebook cell was re-executed; the second run
  (`test_20261020T153852Z`) has byte-identical `predictions.jsonl`. The first
  run is the one scored. M0 is deterministic.
* **M3: API credit ran out.** 87 paragraphs were answered; the remaining 113
  calls were refused ("Your Claude API access is turned off … out of usage
  credits") and returned no response. After credits were added, the same run
  was resumed (`--run-id test_20261020T153852Z`), which sends only paragraphs
  without a cached response. The 87 cached responses were not re-sent or
  changed. Total cost USD 3.37. The `anthropic` SDK was reinstalled in the
  restarted Colab runtime from `claude_data_extractor/requirements.txt`; the SDK
  version of the dev run was not recorded. Model, prompt and schema unchanged.
* **M1, M2: environments rebuilt** in a new Colab runtime from the frozen
  package lists (`evaluation/manifests/env/`); `uv pip freeze` of both rebuilt
  environments was identical to the frozen lists (`M1 ENV SAME`, `M2 ENV SAME`).
  M2 used model revision 4f7bb8b; `chunks_over_limit` 0.
* **M4: Claude Code version.** Claude Code updated itself from 2.1.296 (frozen)
  to **2.1.302** before the first batch. All 20 batches ran with 2.1.302;
  no update was applied during the run. Model Opus 5.5 (`claude-opus-5-5`,
  checked with `/model`), effort "Medium (default)". Agent definition and task
  specification unchanged (sha256 recorded in `run_state.json`).
* **M4: main session behaviour.** In this Claude Code version the main session
  summarised and checked each agent output (counts, JSON validity, quotes) with
  a script of its own and commented on content. It was told after batch_007 to
  only launch the agent. It did not edit any raw file (the files `collect` used
  are listed in `run.json` → `config.raw_files`); its comments were not acted on.
* **M4: batch_008 skipped and run last.** batch_008 (T0071–T0080) had not been
  sent in the main sequence (no raw output). It was run once, at the end, in a
  new Claude Code session (same version and model). There was no earlier output
  of this batch to choose from.
* **M4: read-back corrections.** For batch_005 and batch_006 the agent wrote a
  correction file (`batch_00N.2.json`) during its read-back step; `collect`
  uses the latest correction by design. Records are the same as in the first
  file; only evidence fields differ.
* **M4: evidence quotes.** In T0073 four quotes are not exact substrings of the
  paragraph because the agent dropped private-use characters left by PDF
  parsing (``, ``). Values and materials are correct; scoring does
  not use quotes.
* **M4 tokens and cost:** not measured (Claude Pro subscription session).

## Scoring

`evaluation.score` per run and `evaluation.compare` with M4 as reference:
`results/comparisons/test_20261020T225711Z.md` (primary room-temperature rule,
lenient) and `results/comparisons/test_20261020T225731Z.md` (`--rt-strict`
sensitivity).

## Addendum 2026-10-21 (written before the run below was scored)

While preparing the release, a complete earlier M3 test run was found:
`results/claude/test_20261020T152747Z` (15:27–15:30 UTC, 200 paragraphs, 0 failed,
310 predictions, USD 3.38, same code hashes as the frozen manifest). It came from
the first execution of the notebook cell that ran M0 and M3; the cell was then
executed a second time (M0 `test_20261020T153852Z`, M3 `test_20261020T153852Z`),
and the second M3 run is the one that ran out of API credit. An earlier attempt,
`test_20261020T152547Z`, stopped at start-up (`anthropic` not installed) and made
no API call.

Decision, applied as for M0 and recorded before scoring this run: the **first
complete run is the primary run** — M3 primary = `test_20261020T152747Z`. The
second run (`test_20261020T153852Z`), already scored, is reported as a replicate:
the two runs together give one measurement of run-to-run variation of M3.
