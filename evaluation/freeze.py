"""
Freeze the five methods and the scorer before test annotation (PROTOCOL.md §9).

    python -m evaluation.freeze write --m2-run results/bert/<final dev run>
    python -m evaluation.freeze check --manifest evaluation/manifests/methods_frozen_<date>.json

`write` hashes every file that defines a method or the scoring, records the
external components (commits, model revisions, runner versions), checks that
each method's final dev run was produced by the hashed code, and, only if
every check passes, writes
evaluation/manifests/methods_frozen_<date>.json (never overwritten).
`check` recomputes the hashes and fails if any file differs; it is run before
every test run.
"""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(".")

METHODS = {
    "M0": {"name": "regex baseline (corpus-informed)",
           "files": ["regex_extractor/*.py", "regex_extractor/README.md"],
           "dev_run": "results/regex/dev_20261013T192044Z",
           "external": {"frame_manifest": "evaluation/manifests/regex_frozen_2026-10-13.json"}},
    "M1": {"name": "ChemDataExtractor thermoelectric parsers (Sierepeklis & Cole 2022)",
           "files": ["chem_data_extractor/__init__.py", "chem_data_extractor/predict.py", "chem_data_extractor/README.md"],
           "dev_run": "results/cde/dev_20261016T230248Z",
           "run_hash_key": ("predict_sha256", "chem_data_extractor/predict.py"),
           "external": {"thermoelectricsdb_commit": "78e5003b79f25679f2042407a74f7e88025b3da2",
                        "package_tarball": "chemdataextractor_thermoelectrics/chemdataextractor/dist/ChemDataExtractor-TE-2.0.0-te.tar.gz",
                        "package_tarball_sha256": "5cf7685bd9c81168a3f69fe2fba479a059a04ffc2378ccb758f2043f2a8d7ba9",
                        "python": "3.8.20", "pandas": "1.5.3",
                        "environment_freeze": "evaluation/manifests/env/m1_cde38_freeze.txt"}},
    "M2": {"name": "PolymerNER (MaterialsBERT) + published rule-based linking",
           "files": ["materialsbert_extractor/__init__.py", "materialsbert_extractor/predict.py", "materialsbert_extractor/units.py",
                     "materialsbert_extractor/property_metadata.json", "materialsbert_extractor/README.md",
                     "materialsbert_extractor/vendor/polymer_information_extraction/*"],
           "dev_run": None,   # given on the command line (final run with the frozen code)
           "run_hash_key": ("predict_sha256", "materialsbert_extractor/predict.py"),
           "external": {"model": "pranav-s/PolymerNER",
                        "model_revision": "4f7bb8bd55724ec523e22d6c9793b59ab7e299d0",
                        "pipeline_commit": "d08f2d301fb74c680d8df9b3993d496b069fc6e9",
                        "python": "3.8.20", "chemdataextractor": "1.3.0", "torch": "2.2.2 (CPU)",
                        "transformers": "4.30.2", "spacy": "3.7.5", "en_core_web_sm": "3.7.1",
                        "environment_freeze": "evaluation/manifests/env/m2_m2env_freeze.txt"}},
    "M3": {"name": "Claude, single prompt",
           "files": ["claude_data_extractor/__init__.py", "claude_data_extractor/predict.py",
                     "claude_data_extractor/requirements.txt", "claude_data_extractor/README.md", "evaluation/task_spec.md"],
           "dev_run": "results/claude/dev_20261014T223049Z",
           "run_hash_key": ("predict_sha256", "claude_data_extractor/predict.py"),
           "external": {"model": "claude-opus-5-5", "temperature": "not sent (model default)",
                        "max_tokens": 16000, "runner": "Anthropic Messages API, structured outputs"}},
    "M4": {"name": "Claude agent (pdf-extractor)",
           "files": ["agent_extractor/__init__.py", "agent_extractor/pdf-extractor.md", "agent_extractor/run.py",
                     "agent_extractor/README.md", "evaluation/task_spec.md"],
           "dev_run": "results/agent/dev_20261013T232821Z",
           "run_hash_key": ("agent_sha256", "agent_extractor/pdf-extractor.md"),
           "installed_copy": (".claude/agents/pdf-extractor.md", "agent_extractor/pdf-extractor.md"),
           "external": {"runner": "Claude Code 2.1.296 (WinGet; auto-update off)", "model": "Opus 5.5 (claude-opus-5-5)",
                        "account": "Claude Pro subscription", "batch_size": 10,
                        "request_procedure": "one invocation per batch, request text exactly as printed by run.py prepare; "
                                             "the main session must not review, change or rerun outputs"}},
}
# The protocol keeps a change log and open items after the freeze; its hash at
# freeze time is recorded, but an edit does not invalidate the frozen methods.
INFO_ONLY = {"evaluation/PROTOCOL.md"}
SCORING = ["evaluation/schema.py", "evaluation/score.py", "evaluation/compare.py", "evaluation/check_gold.py",
           "evaluation/diagnose.py", "evaluation/sample.py", "evaluation/PROTOCOL.md", "evaluation/task_spec.md"]


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expand(patterns):
    files = []
    for pat in patterns:
        hits = sorted(p for p in ROOT.glob(pat) if p.is_file() and "__pycache__" not in p.parts)
        if not hits:
            raise SystemExit(f"no file matches {pat}")
        files += hits
    return {p.as_posix(): sha256_file(p) for p in files}


def write(m2_run, out_dir="evaluation/manifests"):
    problems = []
    manifest = {"recorded": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "purpose": "methods and scorer frozen before test annotation (PROTOCOL.md §9); "
                           "every test run is preceded by `python -m evaluation.freeze check`",
                "methods": {}, "scoring": expand(SCORING)}
    for mid, spec in METHODS.items():
        files = expand(spec["files"])
        entry = {"name": spec["name"], "files": files, "external": spec["external"]}
        run = spec["dev_run"] or (m2_run if mid == "M2" else None)
        if run is None:
            problems.append(f"{mid}: no final dev run given")
        else:
            entry["final_dev_run"] = run
            meta = json.loads((Path(run) / "run.json").read_text(encoding="utf-8"))
            if "run_hash_key" in spec:
                key, path = spec["run_hash_key"]
                ran = (meta.get("code_version") or {}).get(key)
                entry["dev_run_produced_by_frozen_code"] = ran == files[path]
                if ran != files[path]:
                    problems.append(f"{mid}: dev run {run} was made with {key}={ran}, current file differs")
        if mid == "M0" and run is not None:
            # same construction as regex_extractor.predict.code_version()
            h = hashlib.sha256()
            for p in sorted(Path("regex_extractor").glob("*.py")):
                h.update(p.name.encode() + b"\0" + p.read_bytes())
            ran = (meta.get("code_version") or {}).get("package_sha256")
            entry["dev_run_produced_by_frozen_code"] = ran == h.hexdigest()
            if ran != h.hexdigest():
                problems.append(f"M0: dev run {run} was made with a different regex_extractor package")
        if mid == "M0":
            frame = json.loads(Path(spec["external"]["frame_manifest"]).read_text(encoding="utf-8"))
            changed = [f for f, h in frame["code"].items() if files.get(f) != h]
            entry["matches_frame_manifest"] = not changed
            if changed:
                problems.append(f"M0: differs from regex_frozen_2026-10-13.json: {changed}")
        if "installed_copy" in spec:
            inst, src = spec["installed_copy"]
            same = Path(inst).exists() and sha256_file(inst) == files[src]
            entry["installed_agent_matches_source"] = same
            if not same:
                problems.append(f"{mid}: {inst} missing or differs from {src}")
        env = spec["external"].get("environment_freeze")
        if env:
            if Path(env).exists():
                entry["environment_freeze_sha256"] = sha256_file(env)
            else:
                problems.append(f"{mid}: environment freeze file {env} missing")
        manifest["methods"][mid] = entry
    if problems:
        print("NOT WRITTEN; fix these first:", *problems, sep="\n  ")
        return None, problems
    out = Path(out_dir) / f"methods_frozen_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"
    if out.exists():
        raise SystemExit(f"{out} exists; not overwriting")
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"-> {out}\nno problems; methods and scorer frozen")
    return out, problems


def check(manifest_path):
    m = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    diffs = []
    groups = [("scoring", m["scoring"])] + [(mid, e["files"]) for mid, e in m["methods"].items()]
    for name, files in groups:
        for f, h in files.items():
            if not Path(f).exists():
                diffs.append(f"{name}: {f} missing")
            elif sha256_file(f) != h:
                if f in INFO_ONLY:
                    print(f"note: {f} edited since the freeze (documentation; recorded, not enforced)")
                else:
                    diffs.append(f"{name}: {f} changed")
    inst, src = METHODS["M4"]["installed_copy"]
    if not Path(inst).exists():
        # Only needed to run M4 with Claude Code; a fresh clone does not have it.
        print(f"note: {inst} not installed (copy {src} there before running M4)")
    elif sha256_file(inst) != m["methods"]["M4"]["files"][src]:
        diffs.append(f"M4: {inst} differs from the frozen agent definition")
    print("FROZEN STATE OK" if not diffs else "NOT FROZEN:", *diffs, sep="\n  ")
    return diffs


def main(argv=None):
    ap = argparse.ArgumentParser(description="Freeze or check methods and scorer")
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("write")
    w.add_argument("--m2-run", required=True)
    c = sub.add_parser("check")
    c.add_argument("--manifest", required=True)
    args = ap.parse_args(argv)
    if args.cmd == "write":
        _, problems = write(args.m2_run)
        raise SystemExit(1 if problems else 0)
    raise SystemExit(1 if check(args.manifest) else 0)


if __name__ == "__main__":
    main()
