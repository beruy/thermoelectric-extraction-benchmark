"""M4 bookkeeping: prepare batches, collect raw agent output into the contract."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from agent_extractor import run as R
from evaluation.schema import validate_prediction


class AgentRun(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        data = self.tmp / "data" / "dev"
        data.mkdir(parents=True)
        rows = [{"sample_id": f"D{i:04d}", "paper_id": "p", "para_id": str(i), "text": f"ZT is 1.{i}"}
                for i in range(1, 6)]
        (data / "inputs.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        self.installed = self.tmp / "installed.md"
        shutil.copy(R.AGENT_SOURCE, self.installed)
        self.out = R.prepare("dev", self.tmp / "data", self.tmp / "results", 2, "dev_test",
                             installed=self.installed)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def write_raw(self, name, paragraphs, suffix=""):
        (self.out / "raw" / f"{name}{suffix}.json").write_text(
            json.dumps({"batch": name, "paragraphs": paragraphs}), encoding="utf-8")

    def rec(self, value, **kw):
        r = {"property": "ZT", "value": value, "value_max": None, "material": "SnSe", "T_K": None,
             "kappa_type": None, "qualifier": None, "origin": "reported", "context": None,
             "doping_text": None, "carrier_conc_cm3": None, "flags": ["approximate_value", "bogus"],
             "evidence": {"quote": f"ZT is {value}", "raw_value": str(value), "raw_unit": None,
                          "conversion": None}}
        r.update(kw)
        return r

    def test_batches_and_refusal_to_overwrite(self):
        state = json.loads((self.out / "run_state.json").read_text())
        self.assertEqual([len(b["sample_ids"]) for b in state["batches"]], [2, 2, 1])
        with self.assertRaises(SystemExit):
            R.prepare("dev", self.tmp / "data", self.tmp / "results", 2, "dev_test", installed=self.installed)

    def test_collect(self):
        self.write_raw("batch_001", [{"sample_id": "D0001", "status": "ok", "records": [self.rec(1.1)]},
                                     {"sample_id": "D0002", "status": "ok", "records": []}])
        self.write_raw("batch_002", [{"sample_id": "D0003", "status": "ok", "records": [self.rec(9.9)]}])
        self.write_raw("batch_002", [{"sample_id": "D0003", "status": "ok", "records": [self.rec(1.3)]},
                                     {"sample_id": "D0004", "status": "error", "records": [], "note": "x"}],
                       suffix=".2")
        meta = R.collect(self.out, model_id="m")
        preds = [json.loads(l) for l in open(self.out / "predictions.jsonl")]
        status = {s["sample_id"]: s for s in map(json.loads, open(self.out / "paragraph_status.jsonl"))}
        self.assertEqual([p["value"] for p in preds], [1.1, 1.3])          # .2 correction used
        self.assertTrue(all(not validate_prediction(p) for p in preds))
        self.assertEqual(preds[0]["flags"], ["approximate_value"])         # unknown flag dropped
        self.assertEqual(preds[0]["evidence"], "ZT is 1.1")
        self.assertEqual(status["D0002"]["n_predictions"], 0)
        self.assertEqual(status["D0004"]["status"], "error")
        self.assertEqual(status["D0005"]["status"], "error")               # batch_003 missing
        self.assertEqual((meta["n_ok"], meta["n_failed"]), (3, 2))
        self.assertIn("batch_003: no raw output", meta["collection_problems"])
        with self.assertRaises(SystemExit):
            R.collect(self.out)


if __name__ == "__main__":
    unittest.main()
