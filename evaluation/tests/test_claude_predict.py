"""M3: single-prompt runner with a fake Messages API client (no network)."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

from claude_data_extractor import predict as M
from evaluation.schema import validate_prediction


class FakeClient:
    def __init__(self, fail_on=()):
        self.calls, self.fail_on = [], set(fail_on)
        self.messages = self

    def create(self, **kw):
        text = kw["messages"][0]["content"]
        self.calls.append(kw)
        if any(f in text for f in self.fail_on):
            raise RuntimeError("boom")
        recs = [] if "nothing" in text else [{
            "property": "ZT", "value": 1.2, "value_max": None, "material": "SnSe", "T_K": 923,
            "kappa_type": None, "qualifier": "MAX", "origin": "reported", "context": "experimental",
            "doping_text": None, "carrier_conc_cm3": None}]
        return NS(model=kw["model"], stop_reason="end_turn",
                  content=[NS(type="thinking", text=None), NS(type="text", text=json.dumps({"records": recs}))],
                  usage=NS(input_tokens=100, output_tokens=50))


class ClaudePredict(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        d = self.tmp / "data" / "dev"
        d.mkdir(parents=True)
        rows = [{"sample_id": "D0001", "paper_id": "p", "para_id": "1", "text": "SnSe ZT 1.2"},
                {"sample_id": "D0002", "paper_id": "p", "para_id": "2", "text": "nothing here"},
                {"sample_id": "D0003", "paper_id": "p", "para_id": "3", "text": "flaky one"}]
        (d / "inputs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_(self, client, run_id=None):
        return M.run("dev", self.tmp / "data", self.tmp / "results", run_id, workers=2, client=client)

    def test_schema_is_strict(self):
        item = M.RECORD_SCHEMA["properties"]["records"]["items"]
        self.assertEqual(set(item["required"]), set(item["properties"]))
        self.assertFalse(item["additionalProperties"])

    def test_resume_and_finish(self):
        c1 = FakeClient(fail_on=["flaky"])
        out, missing = self.run_(c1)
        self.assertEqual(missing, ["D0003"])
        self.assertFalse((out / "run.json").exists())
        c2 = FakeClient()
        out2, missing2 = self.run_(c2, run_id=out.name)
        self.assertEqual((missing2, len(c2.calls)), ([], 1))          # only the failed one re-called
        meta = json.loads((out / "run.json").read_text())
        preds = [json.loads(l) for l in open(out / "predictions.jsonl")]
        status = {s["sample_id"]: s for s in map(json.loads, open(out / "paragraph_status.jsonl"))}
        self.assertEqual((meta["n_ok"], meta["n_failed"], meta["n_predictions"]), (3, 0, 2))
        self.assertEqual(status["D0002"]["n_predictions"], 0)
        self.assertTrue(all(not validate_prediction(p) for p in preds))
        self.assertEqual(preds[0]["qualifier"], "max")                # enum casing normalised
        self.assertEqual(meta["input_tokens"], 300)
        self.assertAlmostEqual(meta["cost_usd"], (300 * 4 + 150 * 20) / 1e6)
        with self.assertRaises(SystemExit):
            self.run_(FakeClient(), run_id=out.name)

    def test_system_prompt_is_task_spec(self):
        c = FakeClient()
        self.run_(c)
        self.assertTrue(c.calls[0]["system"].startswith(M.TASK_SPEC.read_text(encoding="utf-8")))
        self.assertNotIn("temperature", c.calls[0])
        self.assertEqual(c.calls[0]["output_config"]["format"]["type"], "json_schema")


if __name__ == "__main__":
    unittest.main()
