"""
Method M3: Claude, single prompt — one Messages API call per paragraph.

Usage (from the project root, ANTHROPIC_API_KEY set):
    python -m claude_data_extractor.predict --split dev
    python -m claude_data_extractor.predict --split dev --run-id <id>   # resume an interrupted run

Every call sends the same system prompt (evaluation/task_spec.md, shared with M4)
and one paragraph, and requests JSON that follows RECORD_SCHEMA (structured
outputs, `output_config.format`). Raw responses are cached per paragraph in
results/claude/<run_id>/raw/, so an interrupted run resumes without repeating
paid calls. A completed run (run.json present) is never overwritten.

The legacy files of this folder (cli.py, extractor.py, schema.py) predate the
benchmark and are not used here.
"""

import argparse
import hashlib
import json
import os
import platform
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from evaluation.schema import (ALL_PROPERTIES, CONTEXTS, KAPPA_TYPES, ORIGINS, PREDICTION_FIELDS,
                               QUALIFIERS, validate_prediction)

PKG = Path(__file__).resolve().parent
TASK_SPEC = PKG.parent / "evaluation" / "task_spec.md"
DEFAULT_MODEL = "claude-opus-5-5"
# USD per million tokens, from https://platform.claude.com/docs/en/models/overview (read 2026-10-14).
PRICES = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0),
          "claude-fable-5-1": (10.0, 50.0)}
MAX_TOKENS = 16000


def nullable(schema):
    return {"anyOf": [schema, {"type": "null"}]}


def enum_or_null(values):
    return nullable({"type": "string", "enum": list(values)})


RECORD_FIELDS = {
    "property": {"type": "string", "enum": ALL_PROPERTIES},
    "value": nullable({"type": "number"}),
    "value_max": nullable({"type": "number"}),
    "material": nullable({"type": "string"}),
    "T_K": nullable({"type": "number"}),
    "kappa_type": enum_or_null(KAPPA_TYPES),
    "qualifier": enum_or_null(QUALIFIERS),
    "origin": enum_or_null(ORIGINS),
    "context": enum_or_null(CONTEXTS),
    "doping_text": nullable({"type": "string"}),
    "carrier_conc_cm3": nullable({"type": "number"}),
}
RECORD_SCHEMA = {
    "type": "object",
    "properties": {"records": {"type": "array", "items": {
        "type": "object", "properties": RECORD_FIELDS,
        "required": list(RECORD_FIELDS), "additionalProperties": False}}},
    "required": ["records"],
    "additionalProperties": False,
}

SYSTEM_SUFFIX = ("\n\n## Output\n\nReturn only the JSON object required by the response "
                 "schema: {\"records\": [...]}, one record per extracted value, every field "
                 "present (null when unknown). Return {\"records\": []} if the paragraph "
                 "states no target value.")


def system_prompt():
    return TASK_SPEC.read_text(encoding="utf-8") + SYSTEM_SUFFIX


def user_prompt(text):
    return f"<paragraph>\n{text}\n</paragraph>"


def load_dotenv(path=PKG.parent / ".env"):
    """Set variables from a KEY=value .env file in the project root, without
    overriding variables that are already set. The file is never logged."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value and not os.environ.get(key.strip()):
            os.environ[key.strip()] = value


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    return sha256_bytes(Path(path).read_bytes())


def call_model(client, model, system, text, temperature=None):
    kwargs = dict(model=model, max_tokens=MAX_TOKENS, system=system,
                  messages=[{"role": "user", "content": user_prompt(text)}],
                  output_config={"format": {"type": "json_schema", "schema": RECORD_SCHEMA}})
    if temperature is not None:
        kwargs["temperature"] = temperature
    t0 = time.time()
    resp = client.messages.create(**kwargs)
    texts = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    usage = getattr(resp, "usage", None)
    return {"model": getattr(resp, "model", model), "stop_reason": resp.stop_reason,
            "text": texts[-1] if texts else None, "seconds": round(time.time() - t0, 2),
            "input_tokens": getattr(usage, "input_tokens", None),
            "output_tokens": getattr(usage, "output_tokens", None)}


def to_predictions(sample_id, raw):
    """Parse one cached response. Returns (predictions, error or None)."""
    if raw.get("error"):
        return [], raw["error"]
    if raw.get("stop_reason") not in ("end_turn", "stop_sequence"):
        return [], f"stop_reason {raw.get('stop_reason')}"
    try:
        records = json.loads(raw["text"])["records"]
    except (TypeError, KeyError, json.JSONDecodeError) as e:
        return [], f"unparseable response ({e!r})"
    preds = []
    for r in records:
        p = {f: None for f in PREDICTION_FIELDS}
        p.update({k: r.get(k) for k in RECORD_FIELDS})
        for k in ("kappa_type", "qualifier", "origin", "context"):   # enum casing may differ
            if isinstance(p[k], str):
                p[k] = p[k].lower()
        p["sample_id"] = sample_id
        p["flags"] = []
        if p["property"] == "doping" and p["carrier_conc_cm3"] is None and isinstance(p["value"], (int, float)):
            p["carrier_conc_cm3"] = p["value"]
        preds.append(p)
    return preds, None


def run(split, data_dir="evaluation/data", out_root="results", run_id=None, model=DEFAULT_MODEL,
        workers=4, temperature=None, client=None, limit=None):
    inp = Path(data_dir) / split / "inputs.jsonl"
    rows = [json.loads(l) for l in open(inp, encoding="utf-8") if l.strip()]
    if limit:
        rows = rows[:limit]
    run_id = run_id or f"{split}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    out = Path(out_root) / "claude" / run_id
    if (out / "run.json").exists():
        raise SystemExit(f"{out} is complete; runs are never overwritten")
    system = system_prompt()
    state_path = out / "run_state.json"
    state = {"run_id": run_id, "split": split, "model": model, "temperature": temperature,
             "input_sha256": sha256_file(inp), "system_sha256": sha256_bytes(system.encode()),
             "schema_sha256": sha256_bytes(json.dumps(RECORD_SCHEMA, sort_keys=True).encode()),
             "limit": limit}
    if state_path.exists():
        old = json.loads(state_path.read_text(encoding="utf-8"))
        changed = [k for k in state if k != "run_id" and old.get(k) != state[k]]
        if changed:
            raise SystemExit(f"cannot resume {run_id}: {changed} changed since the run started")
        state["started_at"] = old["started_at"]
    else:
        (out / "raw").mkdir(parents=True, exist_ok=True)
        state["started_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

    if client is None:
        import anthropic
        load_dotenv()
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is not set: write it into .env in the project root")
        client = anthropic.Anthropic(max_retries=5)

    todo = [r for r in rows if not (out / "raw" / f"{r['sample_id']}.json").exists()]

    def work(row):
        try:
            raw = call_model(client, model, system, row["text"], temperature)
        except Exception as e:   # recorded per paragraph; the run continues
            raw = {"error": repr(e)[:500]}
        if raw.get("error") or raw.get("stop_reason") in ("max_tokens", "refusal"):
            # not cached: a resumed run tries this paragraph again
            (out / "raw" / f"{row['sample_id']}.failed.json").write_text(json.dumps(raw), encoding="utf-8")
            return row["sample_id"], False
        (out / "raw" / f"{row['sample_id']}.json").write_text(json.dumps(raw, ensure_ascii=False),
                                                                encoding="utf-8")
        return row["sample_id"], True

    print(f"{len(rows) - len(todo)} cached, {len(todo)} to call ({model}, {workers} workers)")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for i, (sid, ok) in enumerate(pool.map(work, todo), start=1):
            if not ok or i % 10 == 0:
                print(f"  {i}/{len(todo)} {sid} {'ok' if ok else 'FAILED (will retry on resume)'}")

    missing = [r["sample_id"] for r in rows if not (out / "raw" / f"{r['sample_id']}.json").exists()]
    if missing:
        print(f"{len(missing)} paragraphs failed: {missing[:10]}. Run the same command with "
              f"--run-id {run_id} to retry them; run.json is written when all succeed or with --finish.")
        return out, missing
    return finish(out, rows, state), []


def finish(out, rows, state):
    """Assemble predictions, paragraph status and run.json from the cached responses."""
    n_ok = n_failed = n_preds = n_invalid = 0
    tin = tout = 0
    seconds, models = 0.0, set()
    with open(out / "predictions.jsonl", "w", encoding="utf-8") as fp, \
         open(out / "paragraph_status.jsonl", "w", encoding="utf-8") as fs:
        for r in rows:
            sid = r["sample_id"]
            path = out / "raw" / f"{sid}.json"
            if not path.exists():
                failed = out / "raw" / f"{sid}.failed.json"
                err = json.loads(failed.read_text())["error"] if failed.exists() else "no response"
                raw = {"error": err or "failed"}
            else:
                raw = json.loads(path.read_text(encoding="utf-8"))
                tin += raw.get("input_tokens") or 0
                tout += raw.get("output_tokens") or 0
                seconds += raw.get("seconds") or 0
                models.add(raw.get("model"))
            preds, err = to_predictions(sid, raw)
            if err:
                fs.write(json.dumps({"sample_id": sid, "status": "error", "n_predictions": 0, "error": err}) + "\n")
                n_failed += 1
                continue
            for p in preds:
                n_invalid += bool(validate_prediction(p))
                fp.write(json.dumps(p, ensure_ascii=False) + "\n")
            fs.write(json.dumps({"sample_id": sid, "status": "ok", "n_predictions": len(preds), "error": None}) + "\n")
            n_ok += 1
            n_preds += len(preds)
    price = PRICES.get(state["model"])
    cost = round(tin / 1e6 * price[0] + tout / 1e6 * price[1], 4) if price else None
    meta = {
        "method_id": "M3", "method_name": "Claude, single prompt (one API call per paragraph)",
        "run_id": state["run_id"], "split": state["split"],
        "code_version": {"predict_sha256": sha256_file(__file__), "system_prompt_sha256": state["system_sha256"],
                         "task_spec_sha256": sha256_file(TASK_SPEC), "schema_sha256": state["schema_sha256"]},
        "config": {"max_tokens": MAX_TOKENS, "structured_output": "output_config.format json_schema",
                   "limit": state.get("limit")},
        "model_id": state["model"],
        "model_params": {"temperature": state["temperature"],
                         "temperature_note": None if state["temperature"] is not None else
                         "not sent (model default); adaptive thinking is always on for this model",
                         "models_reported_by_api": sorted(m for m in models if m)},
        "input_file": str(Path("evaluation/data") / state["split"] / "inputs.jsonl"),
        "input_sha256": state["input_sha256"],
        "started_at": state["started_at"], "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "wall_seconds": round(seconds, 1),
        "n_paragraphs": n_ok + n_failed, "n_ok": n_ok, "n_failed": n_failed,
        "n_predictions": n_preds, "n_invalid_predictions": n_invalid,
        "n_model_calls": n_ok + n_failed, "input_tokens": tin, "output_tokens": tout,
        "cost_usd": cost,
        "price_table": {"usd_per_mtok_in_out": price, "source": "platform.claude.com/docs/en/models/overview, 2026-10-14"},
        "hardware": {"python": platform.python_version(), "machine": platform.machine(), "system": platform.system()},
        "capabilities": ALL_PROPERTIES,
        "measurement_note": "wall_seconds is the sum of per-call times (calls run in parallel); "
                            "output_tokens include thinking tokens as billed.",
    }
    (out / "run.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(json.dumps({k: meta[k] for k in ("run_id", "n_paragraphs", "n_failed", "n_predictions",
                                           "n_invalid_predictions", "input_tokens", "output_tokens",
                                           "cost_usd")}, indent=2))
    print(f"-> {out}")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run M3 (Claude, single prompt)")
    ap.add_argument("--split", required=True, choices=["dev", "test"])
    ap.add_argument("--data", default="evaluation/data")
    ap.add_argument("--out", default="results")
    ap.add_argument("--run-id", help="resume this run")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--temperature", type=float)
    ap.add_argument("--limit", type=int, help="first N paragraphs only (trial run)")
    ap.add_argument("--finish", action="store_true",
                    help="write run.json now; paragraphs still failing are recorded as failed")
    args = ap.parse_args(argv)
    out, missing = run(args.split, args.data, args.out, args.run_id, args.model, args.workers,
                       args.temperature, limit=args.limit)
    if missing and args.finish:
        rows = [json.loads(l) for l in open(Path(args.data) / args.split / "inputs.jsonl", encoding="utf-8") if l.strip()]
        rows = rows[:args.limit] if args.limit else rows
        finish(out, rows, json.loads((out / "run_state.json").read_text(encoding="utf-8")))


if __name__ == "__main__":
    main()
