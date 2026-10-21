# M4 dev run notes: dev_20261013T232821Z

Runner: Claude Code v2.1.296 (WinGet install, Windows), Claude Pro subscription login,
session model shown as "Opus 5.5" (claude-opus-5-5). Auto permission mode; browser tools off.
Agent definition sha256 4916847073…, task_spec sha256 b6e636edbb…, both unchanged since prepare.

## How the batches were run (2026-10-16)

* batch_001 and batch_002: one request each, typed by the annotator in the main session,
  exactly as printed by `run.py prepare`.
* batch_003 … batch_010: one request to the main session asking it to invoke the agent
  sequentially, once per batch, with the same request text and nothing added.
* The main session ran its own read-only checks (JSON parsing, quote matching) after
  batch_001 and batch_002 and commented on some agent decisions. It did not change any
  output file, and the annotator did not act on the comments.

## Deviation: batch_002 was run twice

batch_002 was invoked a second time as part of the queued request and the agent
overwrote raw/batch_002.json, although its definition says never to overwrite.
The first output (4871 bytes, sha256 124e9ec272af2ea1…) had been copied for checking
before the overwrite and is kept here as `batch_002.first_run.json`.
Both runs give the same 8 records (sample_id, property, value, material, T_K identical);
the files differ only in other text fields. The scored run uses the file in raw/
(the second run). Decided before scoring.

## Checks on raw output (before collect)

All 10 batches: paragraphs in batch order, all status "ok", 139 records,
0 contract-invalid records, every evidence quote found verbatim in its paragraph.

## Cost

Run under the Pro subscription; token use and cost not measured (null in run.json).
