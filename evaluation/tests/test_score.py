"""Unit tests for evaluation/score.py on small synthetic data.

Run from the project root:  python -m unittest discover -s evaluation/tests -t .
"""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from evaluation import score as S
from evaluation.schema import GOLD_RECORD_FIELDS, PREDICTION_FIELDS


def pred(sid, prop, value=None, **kw):
    rec = {f: None for f in PREDICTION_FIELDS}
    rec.update(sample_id=sid, property=prop, value=value, flags=[])
    rec.update(kw)
    return rec


def gold(sid, prop, value=None, **kw):
    rec = {f: "" for f in GOLD_RECORD_FIELDS}
    rec.update(sample_id=sid, record_no=1, property=prop,
               value="" if value is None else value)
    rec.update({k: ("" if v is None else v) for k, v in kw.items()})
    return rec


def g(prop, value=None, **kw):
    """Gold dict as load_gold returns it."""
    base = {"sample_id": "X", "property": prop, "material": None, "value": value,
            "value_max": None, "T_K": None, "T_as_written": None, "kappa_type": None,
            "qualifier": None, "origin": None, "context": None, "doping_text": None,
            "carrier_conc_cm3": None, "aliases": []}
    base.update(kw)
    return base


class Criteria(unittest.TestCase):
    def test_value_tolerance_and_zero(self):
        self.assertTrue(S.value_ok({"value": 1.005}, g("ZT", 1.0)))
        self.assertFalse(S.value_ok({"value": 1.02}, g("ZT", 1.0)))
        self.assertTrue(S.value_ok({"value": 0.0}, g("ZT", 0.0)))
        self.assertFalse(S.value_ok({"value": 1e-6}, g("ZT", 0.0)))

    def test_comma_is_rejected(self):
        self.assertEqual(S._num("1.2e20"), 1.2e20)
        with self.assertRaises(ValueError):
            S._num("1,2")

    def test_sign_is_kept(self):
        self.assertFalse(S.value_ok({"value": 100.0}, g("S_uVK", -100.0)))

    def test_range_needs_both_bounds(self):
        gr = g("ZT", 0.5, value_max=1.0)
        self.assertTrue(S.value_ok({"value": 0.5, "value_max": 1.0}, gr))
        self.assertFalse(S.value_ok({"value": 0.5, "value_max": None}, gr))
        self.assertFalse(S.value_ok({"value": 0.5, "value_max": 1.0}, g("ZT", 0.5)))

    def test_temperature(self):
        self.assertTrue(S.temp_ok({"T_K": 300.5}, g("ZT", 1, T_K=300.0)))
        self.assertFalse(S.temp_ok({"T_K": 302.0}, g("ZT", 1, T_K=300.0)))
        self.assertFalse(S.temp_ok({"T_K": None}, g("ZT", 1, T_K=300.0)))
        rt = g("ZT", 1, T_as_written="room temperature")
        self.assertTrue(S.temp_ok({"T_K": None}, rt))
        self.assertTrue(S.temp_ok({"T_K": 300.0}, rt))
        self.assertFalse(S.temp_ok({"T_K": 310.0}, rt))
        self.assertFalse(S.temp_ok({"T_K": 300.0}, g("ZT", 1)))

    def test_kappa_subtype(self):
        self.assertFalse(S.kappa_ok({"kappa_type": None}, g("kappa", 1, kappa_type="lattice")))
        self.assertFalse(S.kappa_ok({"kappa_type": "lattice"}, g("kappa", 1)))
        self.assertTrue(S.kappa_ok({"kappa_type": "unspecified"}, g("kappa", 1, kappa_type="total")))

    def test_material_safe_normalization_only(self):
        self.assertTrue(S.material_ok({"material": "Bi₂Te₃"}, g("ZT", 1, material="Bi2Te3")))
        self.assertTrue(S.material_ok({"material": "Bi_{2} Te_3"}, g("ZT", 1, material="Bi2Te3")))
        self.assertFalse(S.material_ok({"material": "bi2te3"}, g("ZT", 1, material="Bi2Te3")))
        self.assertFalse(S.material_ok({"material": "Te3Bi2"}, g("ZT", 1, material="Bi2Te3")))
        self.assertTrue(S.material_ok({"material": "Te3Bi2"}, g("ZT", 1, material="Bi2Te3"), stoich=True))
        self.assertTrue(S.material_ok({"material": "PPy"}, g("ZT", 1, material="polypyrrole",
                                                             aliases=["PPy"])))
        self.assertTrue(S.material_ok({"material": None}, g("ZT", 1)))
        self.assertFalse(S.material_ok({"material": "SnSe"}, g("ZT", 1)))

    def test_doping(self):
        self.assertTrue(S.doping_ok({"doping_text": "2% Na"}, g("doping", doping_text="Na-doped")))
        self.assertFalse(S.doping_ok({"doping_text": "K"}, g("doping", doping_text="Na-doped")))
        self.assertTrue(S.doping_ok({"carrier_conc_cm3": 1.04e20},
                                    g("doping", carrier_conc_cm3=1e20)))

    def test_matching_is_optimal_not_greedy(self):
        # p0 fits both golds, p1 fits only g0: greedy p0->g0 would leave p1 unmatched
        preds = [{"v": {0, 1}}, {"v": {0}}]
        golds = [0, 1]
        m = S.max_matching(preds, golds, lambda p, gg: gg in p["v"])
        self.assertEqual(len(m), 2)


class EndToEnd(unittest.TestCase):
    IDS = ["T0001", "T0002", "T0003", "T0004", "T0005"]

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.data = root / "data"
        priv = self.data / "test" / "private"
        priv.mkdir(parents=True)
        key = [
            {"sample_id": "T0001", "paper_id": "A", "stratum": "ZT", "in_scope": True, "weight": 10.0},
            {"sample_id": "T0002", "paper_id": "B", "stratum": "S_uVK", "in_scope": True, "weight": 2.0},
            {"sample_id": "T0003", "paper_id": "B", "stratum": "in_scope_no_hit", "in_scope": True, "weight": 50.0},
            {"sample_id": "T0004", "paper_id": "C", "stratum": "out_of_scope", "in_scope": False, "weight": 900.0},
            {"sample_id": "T0005", "paper_id": "C", "stratum": "kappa", "in_scope": True, "weight": 5.0},
        ]
        with open(priv / "sample_key.jsonl", "w") as f:
            for k in key:
                f.write(json.dumps(k) + "\n")
        with open(self.data / "test" / "inputs.jsonl", "w") as f:
            for k in key:
                f.write(json.dumps({"sample_id": k["sample_id"], "paper_id": k["paper_id"],
                                    "para_id": "p", "text": "x"}) + "\n")
        self.input_sha = S.sha256_file(self.data / "test" / "inputs.jsonl")
        self.golds = [
            gold("T0001", "ZT", 1.2, material="SnSe", T_K=923),
            gold("T0001", "ZT", 0.8, material="SnSe", T_K=300, record_no=2),
            gold("T0002", "S_uVK", -150, material="Bi2Te3", T_as_written="room temperature"),
            gold("T0003", "NONE"),
            gold("T0004", "NONE"),
            gold("T0005", "kappa", 0.4, material="PbTe", T_K=700, kappa_type="lattice"),
        ]
        self.write_gold(self.golds)
        self.run = root / "run"
        self.run.mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write_gold(self, rows):
        gdir = self.data / "test" / "gold"
        gdir.mkdir(parents=True, exist_ok=True)
        with open(gdir / "gold_records.csv", "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=GOLD_RECORD_FIELDS)
            w.writeheader()
            w.writerows(rows)

    def write_run(self, preds, status=None, capabilities=None, **meta):
        status = status or {s: "ok" for s in self.IDS}
        with open(self.run / "predictions.jsonl", "w") as f:
            for p in preds:
                f.write(json.dumps(p) + "\n")
        with open(self.run / "paragraph_status.jsonl", "w") as f:
            for sid, st in status.items():
                f.write(json.dumps({"sample_id": sid, "status": st, "n_predictions": sum(p.get("sample_id") == sid for p in preds),
                                    "error": None}) + "\n")
        run = {"method_id": "M_test", "run_id": "r1", "split": "test",
               "input_sha256": self.input_sha,
               "capabilities": capabilities or ["ZT", "S_uVK", "kappa", "sigma", "PF", "doping"]}
        run.update(meta)
        (self.run / "run.json").write_text(json.dumps(run))

    def assert_not_scored(self, needle):
        with self.assertRaises(S.ScoringError) as cm:
            S.score("test", self.run, self.data, reps=50)
        self.assertTrue(any(needle in e for e in cm.exception.errors), cm.exception.errors)

    def test_scores(self):
        preds = [
            pred("T0001", "ZT", 1.2, material="SnSe", T_K=923),       # L3 TP
            pred("T0001", "ZT", 1.2, material="SnSe", T_K=923),       # duplicate -> collapsed
            pred("T0001", "ZT", 0.8, material="SnSe", T_K=None),      # L1 only (T missing)
            pred("T0002", "S_uVK", 150, material="Bi2Te3"),           # sign error -> FP+FN
            pred("T0003", "ZT", 2.0, material="X"),                   # FP on empty paragraph
            pred("T0004", "ZT", 1.0),                                 # control stratum
            pred("T0005", "kappa", 0.4, material="PbTe", T_K=700),    # wrong kappa type
        ]
        self.write_run(preds)
        s = S.score("test", self.run, self.data, reps=200)
        core = s["scores"]["core_all"]
        self.assertEqual(core["L3"]["sample_level"]["tp"], 1)
        self.assertEqual(core["L1"]["sample_level"]["tp"], 2)
        self.assertEqual(core["L3"]["sample_level"]["fp"], 4)
        self.assertEqual(core["L3"]["sample_level"]["fn"], 3)
        self.assertAlmostEqual(core["L3"]["corpus_level"]["tp"], 10.0)
        self.assertAlmostEqual(core["L3"]["corpus_level"]["fp"], 10 + 2 + 50 + 5)
        self.assertAlmostEqual(core["L3"]["corpus_level"]["fn"], 10 + 2 + 5)
        self.assertAlmostEqual(core["L3"]["sample_level"]["f1"], 2 / (2 + 4 + 3))
        self.assertEqual(s["secondary"]["duplicates_collapsed"], 1)
        self.assertEqual(s["secondary"]["diagnostics"]["sign_errors"], {"S_uVK": 1})
        self.assertEqual(s["control_stratum"], {"paragraphs": 1, "gold_records": 0, "predictions": 1})

    def test_confidence_intervals_everywhere(self):
        self.write_run([pred("T0001", "ZT", 1.2, material="SnSe", T_K=923)])
        s = S.score("test", self.run, self.data, reps=200)
        for level in ("sample_level", "corpus_level"):
            ci = s["scores"]["core_all"]["L3"][level]["ci95_paper_bootstrap"]
            self.assertIsNotNone(ci["f1"])
            self.assertEqual(ci["reps"], 200)
            self.assertIn("ci95_paper_bootstrap", s["per_property_L3"]["ZT"][level])
        self.assertIn("sample_level", s["secondary"]["stoichiometry_aware_L3_core"])

    def test_zero_predictions_give_f1_zero(self):
        self.write_run([])
        s = S.score("test", self.run, self.data, reps=200)
        e = s["scores"]["core_all"]["L3"]["sample_level"]
        self.assertEqual(e["f1"], 0.0)
        self.assertEqual(e["recall"], 0.0)
        self.assertIsNone(e["precision"])   # undefined: no predictions at all
        ci = e["ci95_paper_bootstrap"]
        self.assertEqual(ci["f1"], [0.0, 0.0])            # no resample dropped
        self.assertEqual(ci["undefined_resamples"].get("f1"), None)

    def test_invalid_prediction_never_matches(self):
        bad = {"sample_id": "T0001", "property": "ZT", "value": 1.2, "material": "SnSe",
               "T_K": 923}                                    # required fields missing
        unknown_prop = pred("T0003", "Seebeck", 100.0)
        self.write_run([bad, unknown_prop])
        s = S.score("test", self.run, self.data, reps=50)
        e = s["scores"]["core_all"]["L3"]["sample_level"]
        self.assertEqual(e["tp"], 0)
        self.assertEqual(e["fp"], 2)
        self.assertEqual(s["secondary"]["invalid_prediction_records"], 2)

    def test_non_string_text_fields_are_false_positives(self):
        for field, value in (("material", ["SnSe"]), ("material", 5), ("doping_text", {"x": 1}),
                             ("evidence", ["a"]), ("flags", [1])):
            with self.subTest(field=field, value=value):
                record = pred("T0001", "ZT", 1.2, material="SnSe", T_K=923)
                record[field] = value
                self.write_run([record])
                result = S.score("test", self.run, self.data, reps=0)
                counts = result["scores"]["core_all"]["L3"]["sample_level"]
                self.assertEqual(counts["tp"], 0)
                self.assertEqual(counts["fp"], 1)
                self.assertEqual(result["secondary"]["invalid_prediction_records"], 1)

    def test_non_string_prediction_id_stops_scoring(self):
        self.write_run([pred(["T0001"], "ZT", 1.2)])
        self.assert_not_scored("non-string sample_id")

    def test_duplicate_gold_row_stops_scoring(self):
        rows = [dict(g) for g in self.golds]
        rows.append(dict(rows[0]))
        self.write_gold(rows)
        self.write_run([pred("T0001", "ZT", 1.2, material="SnSe", T_K=923)])
        self.assert_not_scored("duplicate (sample_id, record_no)")

    def test_failed_paragraph_and_unsupported(self):
        preds = [pred("T0001", "ZT", 1.2, material="SnSe", T_K=923),
                 pred("T0005", "kappa", 0.4, material="PbTe", T_K=700, kappa_type="lattice")]
        status = {s: "ok" for s in self.IDS}
        status["T0005"] = "error"
        self.write_run(preds, status, capabilities=["ZT", "S_uVK", "sigma", "PF"])
        s = S.score("test", self.run, self.data, reps=200)
        self.assertEqual(s["n_paragraphs"]["failed"], 1)
        self.assertEqual(s["secondary"]["predictions_ignored_on_failed_paragraphs"], 1)
        self.assertEqual(s["scores"]["core_all"]["L3"]["sample_level"]["fn"], 3)
        self.assertEqual(s["scores"]["core_supported_only"]["L3"]["sample_level"]["fn"], 2)
        self.assertEqual(s["per_property_L3"]["kappa"]["status"], "not supported")
        self.assertEqual(s["scores"]["extended_doping"], "not supported")

    def test_gold_enum_typos_stop_scoring(self):
        for field, value in (("kappa_type", "latice"), ("qualifier", "maximum"),
                             ("origin", "reportd"), ("context", "expermental")):
            with self.subTest(field=field):
                rows = [dict(g) for g in self.golds]
                rows[-1][field] = value
                self.write_gold(rows)
                self.write_run([])
                self.assert_not_scored(field)

    def test_nonfinite_gold_stops_scoring(self):
        for field in ("value", "value_max", "T_K", "carrier_conc_cm3"):
            for value in ("nan", "inf", "-inf", "1e999", "True"):
                with self.subTest(field=field, value=value):
                    rows = [dict(g) for g in self.golds]
                    rows[0][field] = value
                    self.write_gold(rows)
                    self.write_run([])
                    self.assert_not_scored("not a number")

    def test_invalid_numeric_predictions_are_false_positives(self):
        for field in ("value", "value_max", "T_K", "carrier_conc_cm3"):
            for value in (True, False, float("nan"), float("inf"), -float("inf")):
                with self.subTest(field=field, value=value):
                    record = pred("T0001", "ZT", 1.2, material="SnSe", T_K=923)
                    record[field] = value
                    self.write_run([record])
                    result = S.score("test", self.run, self.data, reps=0)
                    counts = result["scores"]["core_all"]["L3"]["sample_level"]
                    self.assertEqual(counts["tp"], 0)
                    self.assertEqual(counts["fp"], 1)
                    self.assertEqual(result["secondary"]["invalid_prediction_records"], 1)

    def test_prediction_count_mismatch_stops_scoring(self):
        for declared in (3, -1, True, 1.5, None):
            with self.subTest(declared=declared):
                self.write_run([])
                path = self.run / "paragraph_status.jsonl"
                rows = S.load_jsonl(path)
                rows[0]["n_predictions"] = declared
                path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
                self.assert_not_scored("n_predictions")

    def test_duplicate_status_stops_scoring(self):
        self.write_run([])
        path = self.run / "paragraph_status.jsonl"
        first = path.read_text().splitlines()[0]
        with path.open("a") as f:
            f.write(first + "\n")
        self.assert_not_scored("duplicate paragraph status")

    def test_missing_gold_stops_scoring(self):
        self.write_gold([g for g in self.golds if g["sample_id"] == "T0001"])
        self.write_run([pred("T0001", "ZT", 1.2, material="SnSe", T_K=923)])
        self.assert_not_scored("no gold row")

    def test_invalid_gold_stops_scoring(self):
        rows = [dict(g) for g in self.golds]
        rows[0]["value"] = "1,2"
        self.write_gold(rows)
        self.write_run([])
        self.assert_not_scored("not a number")

    def test_wrong_input_hash_stops_scoring(self):
        self.write_run([], input_sha256="0" * 64)
        self.assert_not_scored("input_sha256")

    def test_wrong_split_stops_scoring(self):
        self.write_run([], split="dev")
        self.assert_not_scored("split")

    def test_incomplete_run_stops_scoring(self):
        status = {s: "ok" for s in self.IDS[:-1]}
        self.write_run([], status)
        self.assert_not_scored("no line in paragraph_status")

    def test_unknown_prediction_id_stops_scoring(self):
        self.write_run([pred("T9999", "ZT", 1.0)])
        self.assert_not_scored("unknown sample_ids")


if __name__ == "__main__":
    unittest.main()


class TestRoomTemperatureRule(unittest.TestCase):
    def test_lenient_and_strict(self):
        from evaluation import score as S
        gold = {"T_K": None, "T_as_written": "room temperature"}
        none_gold = {"T_K": None, "T_as_written": ""}
        num_gold = {"T_K": 295.0, "T_as_written": "295 K"}
        old = S.RT_ACCEPT_NUMERIC
        try:
            S.RT_ACCEPT_NUMERIC = True
            self.assertTrue(S.temp_ok({"T_K": None}, gold))
            self.assertTrue(S.temp_ok({"T_K": 293.0}, gold))
            self.assertTrue(S.temp_ok({"T_K": 300.0}, gold))
            self.assertFalse(S.temp_ok({"T_K": 301.0}, gold))
            self.assertFalse(S.temp_ok({"T_K": 295.0}, none_gold))
            self.assertFalse(S.temp_ok({"T_K": None}, num_gold))
            S.RT_ACCEPT_NUMERIC = False
            self.assertTrue(S.temp_ok({"T_K": None}, gold))
            self.assertFalse(S.temp_ok({"T_K": 295.0}, gold))
        finally:
            S.RT_ACCEPT_NUMERIC = old
