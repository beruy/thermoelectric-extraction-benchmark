# agent_extractor — method M4 (Claude agent)

M4 is the `pdf-extractor` Claude Code subagent run on the benchmark paragraphs.
It differs from M3 (single prompt, same model) only in its agent components:
batch processing with a file-based workflow, an evidence quote for every
record, and a read-back check of its own output. Both methods receive the same
task definition, `evaluation/task_spec.md` (PROTOCOL.md §1, §10).

## Files

| File | Role |
|---|---|
| `pdf-extractor.md` | agent definition (source of truth) |
| `run.py` | `prepare`: split `inputs.jsonl` into batches; `collect`: turn raw agent output into the contract |
| `../evaluation/task_spec.md` | task definition shared with M3 |

The agent may read only `evaluation/task_spec.md` and the batch file it is
given; its tools are limited to Read and Write. It does not read
`regex_extractor`, `evaluation/data/` (gold, sample keys) or other runs.

## Run

Claude Code loads subagents only from `.claude/agents/`, at session start.

```powershell
# from the arxiv folder
Copy-Item "agent_extractor\pdf-extractor.md" ".claude\agents\pdf-extractor.md" -Force
python -m agent_extractor.run prepare --split dev --batch-size 10
```

`prepare` refuses to run if the installed copy differs from
`pdf-extractor.md`. It writes `results/agent/<run_id>/batches/` and prints one
request per batch. Open a **new** Claude Code session in the arxiv folder and
send the requests one by one; each request starts the agent with a fresh
context. Note the model shown in the session and, if available, the token and
cost figures (`/cost`). Then:

```powershell
python -m agent_extractor.run collect --run results/agent/<run_id> --model-id <model> `
    --input-tokens <n> --output-tokens <n> --cost-usd <x>
python -m evaluation.score --split dev --run results/agent/<run_id>
```

Token and cost arguments are optional; without them the fields are null and
the paper reports cost as not measured for M4. A paragraph missing from the
raw output, or marked `error` by the agent, is recorded as a failed paragraph.

## Status

| Former gap | Resolution (2026-10-14) |
|---|---|
| Schema reference to `regex_extractor/schema.py` | task definition in `evaluation/task_spec.md`; no code read by the agent |
| Input with `source`, `para_kind` | batches of `inputs.jsonl` lines (`sample_id`, `paper_id`, `para_id`, `text`) |
| Output in `Claude outputs/extracted/` | raw JSON per batch → `run.py collect` → `predictions.jsonl`, `paragraph_status.jsonl`, `run.json` |
| kappa subtype in `qualifier` | `kappa_type`; `origin`, `context`; qualifier `max/min/avg/range` |
| Dependency on M0 (scope rule, flag names) | removed: no scope filter, own flag vocabulary |
| No cost record | invocations counted; tokens and cost from the session when available |

Known design limits, reported in the paper: paragraphs are processed in
batches of 10 within one agent context (the agent is told to treat them
independently); the model is the session model (`model: inherit`) and is
recorded per run; temperature is not controllable in Claude Code.

## Legacy pieces (not used by the benchmark)

* `Claude outputs/build_results.py`, `Claude outputs/results/results.csv`:
  pre-benchmark results table from the agent's former PDF-mode output.
* `Claude outputs/agent_update/`, `Claude outputs/old-reruns/`: earlier
  definitions and PDF-mode runs, kept as evidence of prompt sensitivity.
* PDF mode was removed from the definition; the full-PDF experiment
  (PROTOCOL.md §10) will get its own definition.
