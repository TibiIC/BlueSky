"""Run with: .venv/bin/python -m unittest discover tests"""

import os
import unittest

from fastapi.testclient import TestClient

from climate_lens.app import app
from climate_lens.calculations import evaluate, netting_economics
from climate_lens.data import FIELD_CASES, NET_SIGNAL, NET_STAGE
from climate_lens.report import build_report

client = TestClient(app)
os.environ.pop("GEMINI_API_KEY", None)  # never call Gemini from tests


class Calculations(unittest.TestCase):
    def test_evaluate_peas_defaults(self):
        r = evaluate(area=100, yield_low=4, yield_high=5, demand=500, premium=40, action_cost=1200, baseline_co2=82)
        self.assertEqual(r["usable"], (400, 500))
        self.assertEqual(r["gap"], (100, 0))
        self.assertEqual(r["cost"], (4000, 0))
        self.assertEqual(r["break_even"], 30)
        self.assertIsNone(r["after"])

    def test_evaluate_rejects_inverted_yields(self):
        with self.assertRaises(ValueError):
            evaluate(area=1, yield_low=5, yield_high=4, demand=1, premium=1, action_cost=1, baseline_co2=1)

    def test_netting_defaults(self):
        r = netting_economics(area=5, price=1200, seasons=4, labor=200, value=250, saved=10)
        self.assertEqual(r["seasonal_cost_eur"], 2500)
        self.assertEqual(r["break_even_tonnes"], 10)
        self.assertEqual(r["net_gain_eur"], 0)


class Reports(unittest.TestCase):
    def test_every_stage_and_observation_builds(self):
        for case, field in FIELD_CASES.items():
            for stage, observations in field["stages"].items():
                for observation in observations:
                    with self.subTest(case=case, stage=stage, observation=observation):
                        build_report(case, stage, observation)

    def test_carrot_netting_only_for_netting_recommendation(self):
        self.assertEqual(build_report("satakunta-carrots", NET_STAGE, NET_SIGNAL)["impact"]["kind"], "netting")
        self.assertEqual(build_report("satakunta-carrots", "Later growth")["impact"]["kind"], "none")

    def test_rapeseed_outside_escalation_gate(self):
        r = build_report("kantvik-rapeseed", checks={"monitoring": True, "threshold_met": True})
        self.assertEqual(r["escalation"]["status"], "Outside this pest-control workflow")

    def test_escalation_refers_to_adviser_when_all_checks_pass(self):
        r = build_report("sakyla-peas", checks=dict(monitoring=True, threshold_met=True, alternatives_insufficient=True))
        self.assertEqual(r["escalation"]["status"], "Refer to a qualified adviser for review")


class Api(unittest.TestCase):
    def test_options(self):
        cases = client.get("/reports/options").json()
        self.assertEqual([c["id"] for c in cases], ["satakunta-carrots", "sakyla-peas", "kantvik-rapeseed"])

    def test_json_report_with_overrides(self):
        res = client.post("/reports", json={"case": "sakyla-peas", "impact": {"area": 120}, "recovered": 50})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["impact"]["result"]["usable"], [480, 600])
        self.assertNotIn("ai", res.json())

    def test_invalid_selection_is_422(self):
        self.assertEqual(client.post("/reports", json={"case": "nope"}).status_code, 422)
        self.assertEqual(client.post("/reports", json={"case": "sakyla-peas", "stage": "Winter"}).status_code, 422)
        self.assertEqual(client.post("/reports", json={"case": "sakyla-peas", "impact": {"yield_low": 9}}).status_code, 422)

    def test_html_report_escapes_question(self):
        res = client.get("/reports/view", params={"case": "satakunta-carrots", "explain": True, "question": "<script>x</script>"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("Fit insect netting before exposure", res.text)
        self.assertNotIn("<script>x</script>", res.text)

    def test_studio_page(self):
        res = client.get("/studio")
        self.assertEqual(res.status_code, 200)
        self.assertIn("Field Operations", res.text)

    def test_index(self):
        self.assertIn("/reports/view?case=sakyla-peas", client.get("/").text)


if __name__ == "__main__":
    unittest.main()
