# claude_data_extractor — method M3 (Claude, single prompt)

`predict.py` sends one Messages API call per benchmark paragraph. The system
prompt is `evaluation/task_spec.md` (shared with M4) plus a short output
instruction; the answer is constrained to `RECORD_SCHEMA` with structured
outputs (`output_config.format`). No examples, no tools, no retries of content.

```bash
pip install -r claude_data_extractor/requirements.txt
export ANTHROPIC_API_KEY=...            # in Colab: from the Secrets panel
python -m claude_data_extractor.predict --split dev --limit 3   # trial, not scorable
python -m claude_data_extractor.predict --split dev
python -m evaluation.score --split dev --run results/claude/<run_id>
```

* Default model `claude-opus-5-5` (same as the M4 session). Prices for the cost
  record are in `PRICES` (source and date in the code).
* Temperature is not sent unless `--temperature` is given; the model's adaptive
  thinking is always on. Both are recorded in `run.json`.
* Responses are cached in `results/claude/<run_id>/raw/`. If a run is
  interrupted or some calls fail, run the same command with `--run-id <run_id>`:
  only missing paragraphs are called again. `--finish` writes `run.json` with
  the remaining failures recorded as failed paragraphs.
