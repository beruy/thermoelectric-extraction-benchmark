"""
Run bookkeeping for M4 (Claude agent) on the benchmark contract.

The agent itself runs inside Claude Code (agent_extractor/pdf-extractor.md,
installed in .claude/agents/). This module prepares its input batches and turns
its raw output into the method contract (PROTOCOL.md §8).

    # 1. prepare a run: split inputs.jsonl into batches, record hashes
    python -m agent_extractor.run prepare --split dev --batch-size 10

    # 2. in a NEW Claude Code session, for each batch, send the printed request
    #    (one batch per request)

    # 3. collect: validate raw output, write predictions/status/run.json
    python -m agent_extractor.run collect --run results/agent/<run_id> \
        --model-id <model shown in the session> [--input-tokens N --output-tokens N --cost-usd X]

Runs are never overwritten. A paragraph missing from the raw output, or marked
status "error" by the agent, is a failed paragraph (all its gold records count
as misses), not an empty extraction.
"""

import argparse
import hashlib
import json
import platform
import re
from datetime import datetime, timezone
from pathlib import Path

from evaluation.schema import ALL_PROPERTIES, PREDICTION_FIELDS, validate_prediction

PKG = Path(__file__).resolve().parent
AGENT_SOURCE = PKG / "pdf-extractor.md"
TASK_SPEC = PKG.parent / "evaluation" / "task_spec.md"
FLAGS = {"approximate_value", "temperature_unspecified", "derived_from_resistivity",
         "ambiguous_attribution", "combined_sources", "partial_evidence"}
REQUEST = ("Use the pdf-extractor agent. Batch file: {batch}. "
           "Write its output to: {out}.")


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def now():
    return datetime.now(timezone.utc)


def prepare(split, data_dir, out_root, batch_size, run_id=None, installed=None):
    inp = Path(data_dir) / split / "inputs.jsonl"
    run_id = run_id or f"{split}_{now().strftime('%Y%m%dT%H%M%SZ')}"
    out = Path(out_root) / "agent" / run_id
    if out.exists():
        raise SystemExit(f"{out} exists; runs are never overwritten")
    installed = Path(installed or PKG.parent / ".claude" / "agents" / "pdf-extractor.md")
    if not installed.exists() or sha256_file(installed) != sha256_file(AGENT_SOURCE):
        raise SystemExit(f"{installed} is missing or differs from {AGENT_SOURCE}; install it "
                         "and start a new Claude Code session first (see README)")
    rows = [json.loads(l) for l in open(inp, encoding="utf-8") if l.strip()]
    (out / "batches").mkdir(parents=True)
    (out / "raw").mkdir()
    batches = []
    for b, start in enumerate(range(0, len(rows), batch_size), start=1):
        name = f"batch_{b:03d}"
        path = out / "batches" / f"{name}.jsonl"
        with open(path, "w", encoding="utf-8") as f:
            for r in rows[start:start + batch_size]:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        batches.append({"batch": name, "sample_ids": [r["sample_id"] for r in rows[start:start + batch_size]]})
    state = {"run_id": run_id, "split": split, "prepared_at": now().isoformat(timespec="seconds"),
             "input_file": str(inp), "input_sha256": sha256_file(inp), "batch_size": batch_size,
             "agent_sha256": sha256_file(AGENT_SOURCE), "task_spec_sha256": sha256_file(TASK_SPEC),
             "batches": batches}
    (out / "run_state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")
    print(f"-> {out}\n\nIn a new Claude Code session, send one request per batch "
          "(each request starts the agent with a fresh context):\n")
    for b in batches:
        print(REQUEST.format(batch=(out / "batches" / f"{b['batch']}.jsonl").as_posix(),
                             out=(out / "raw" / f"{b['batch']}.json").as_posix()))
    return out


def latest_raw(raw_dir, name):
    """batch_001.json, or the highest batch_001.N.json correction written by the agent."""
    cands = [p for p in raw_dir.glob(f"{name}*.json")
             if re.fullmatch(rf"{name}(\.\d+)?\.json", p.name)]
    if not cands:
        return None
    return max(cands, key=lambda p: int(p.name.split(".")[1]) if p.name.count(".") == 2 else 1)


def to_prediction(sample_id, rec):
    p = {f: None for f in PREDICTION_FIELDS}
    for f in PREDICTION_FIELDS:
        if f in rec and f not in ("sample_id", "flags", "evidence"):
            p[f] = rec[f]
    p["sample_id"] = sample_id
    p["flags"] = [f for f in rec.get("flags") or [] if f in FLAGS]
    ev = rec.get("evidence")
    p["evidence"] = ev.get("quote") if isinstance(ev, dict) else (ev if isinstance(ev, str) else None)
    if p["property"] == "doping" and p["carrier_conc_cm3"] is None and isinstance(p["value"], (int, float)):
        p["carrier_conc_cm3"] = p["value"]
    return p


def collect(run_dir, model_id=None, input_tokens=None, output_tokens=None, cost_usd=None,
            price_table=None):
    run_dir = Path(run_dir)
    state = json.loads((run_dir / "run_state.json").read_text(encoding="utf-8"))
    if (run_dir / "run.json").exists():
        raise SystemExit(f"{run_dir/'run.json'} exists; runs are never overwritten")
    if sha256_file(state["input_file"]) != state["input_sha256"]:
        raise SystemExit("inputs.jsonl changed since prepare")
    n_ok = n_failed = n_preds = n_invalid = 0
    used, problems = {}, []
    with open(run_dir / "predictions.jsonl", "w", encoding="utf-8") as fp, \
         open(run_dir / "paragraph_status.jsonl", "w", encoding="utf-8") as fs:
        for b in state["batches"]:
            raw_path = latest_raw(run_dir / "raw", b["batch"])
            got = {}
            if raw_path is None:
                problems.append(f"{b['batch']}: no raw output")
            else:
                used[b["batch"]] = raw_path.name
                try:
                    raw = json.loads(raw_path.read_text(encoding="utf-8"))
                    for par in raw.get("paragraphs", []):
                        if par.get("sample_id") in got:
                            problems.append(f"{b['batch']}: duplicate {par.get('sample_id')}")
                        got[par.get("sample_id")] = par
                except (json.JSONDecodeError, AttributeError) as e:
                    problems.append(f"{b['batch']}: invalid JSON ({e})")
                    got = {}
            for sid in b["sample_ids"]:
                par = got.get(sid)
                if par is None or par.get("status") != "ok" or not isinstance(par.get("records"), list):
                    err = "missing from raw output" if par is None else (par.get("note") or "agent status not ok")
                    fs.write(json.dumps({"sample_id": sid, "status": "error", "n_predictions": 0,
                                         "error": err}) + "\n")
                    n_failed += 1
                    continue
                preds = [to_prediction(sid, r) for r in par["records"] if isinstance(r, dict)]
                for p in preds:
                    if validate_prediction(p):
                        n_invalid += 1
                    fp.write(json.dumps(p, ensure_ascii=False) + "\n")
                fs.write(json.dumps({"sample_id": sid, "status": "ok", "n_predictions": len(preds),
                                     "error": None}) + "\n")
                n_ok += 1
                n_preds += len(preds)
            extra = set(got) - set(b["sample_ids"])
            if extra:
                problems.append(f"{b['batch']}: unknown sample_ids {sorted(extra)[:5]} ignored")
    meta = {
        "method_id": "M4", "method_name": "Claude agent (pdf-extractor, blind paragraph batches)",
        "run_id": state["run_id"], "split": state["split"],
        "code_version": {"agent_sha256": state["agent_sha256"],
                         "task_spec_sha256": state["task_spec_sha256"],
                         "run_py_sha256": sha256_file(__file__),
                         "agent_unchanged_since_prepare": sha256_file(AGENT_SOURCE) == state["agent_sha256"]},
        "config": {"batch_size": state["batch_size"], "raw_files": used},
        "model_id": model_id, "model_params": {"runner": "Claude Code subagent", "temperature": None},
        "input_file": state["input_file"], "input_sha256": state["input_sha256"],
        "started_at": state["prepared_at"], "finished_at": now().isoformat(timespec="seconds"),
        "wall_seconds": None,
        "n_paragraphs": n_ok + n_failed, "n_ok": n_ok, "n_failed": n_failed,
        "n_predictions": n_preds, "n_invalid_predictions": n_invalid,
        "n_model_calls": len(used), "input_tokens": input_tokens, "output_tokens": output_tokens,
        "cost_usd": cost_usd, "price_table": price_table,
        "hardware": {"python": platform.python_version(), "machine": platform.machine(),
                     "system": platform.system()},
        "capabilities": ALL_PROPERTIES,
        "collection_problems": problems,
        "measurement_note": "n_model_calls counts agent invocations (one per batch). Tokens and cost "
                            "are entered from the Claude Code session if available, else null; "
                            "wall time is not measured for interactive runs.",
    }
    (run_dir / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("run_id", "n_paragraphs", "n_failed", "n_predictions",
                                           "n_invalid_predictions", "collection_problems")}, indent=2))
    return meta


def main(argv=None):
    ap = argparse.ArgumentParser(description="M4 run bookkeeping")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--split", required=True, choices=["dev", "test"])
    p.add_argument("--data", default="evaluation/data")
    p.add_argument("--out", default="results")
    p.add_argument("--batch-size", type=int, default=10)
    p.add_argument("--run-id")
    c = sub.add_parser("collect")
    c.add_argument("--run", required=True)
    c.add_argument("--model-id")
    c.add_argument("--input-tokens", type=int)
    c.add_argument("--output-tokens", type=int)
    c.add_argument("--cost-usd", type=float)
    args = ap.parse_args(argv)
    if args.cmd == "prepare":
        prepare(args.split, args.data, args.out, args.batch_size, args.run_id)
    else:
        collect(args.run, args.model_id, args.input_tokens, args.output_tokens, args.cost_usd)


if __name__ == "__main__":
    main()
