# results

One folder per method (`regex/`, `cde/`, `polymerner/`, `claude/`, `agent/`),
one subfolder per run (`<split>_<UTC timestamp>`). A run folder holds
`predictions.jsonl`, `paragraph_status.jsonl`, `run.json` and, after scoring,
`scores/`. Run folders and score files are never overwritten.
