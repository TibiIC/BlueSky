"""Run with: .venv/bin/python -m unittest discover tests"""

import os
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from climate_lens import llm, sbtn
from climate_lens.app import app

client = TestClient(app)
for var in ("GEMINI_API_KEY", "SNOWFLAKE_ACCOUNT", "SNOWFLAKE_PAT", "LLM_PROVIDER"):
    os.environ.pop(var, None)  # never call a real LLM from tests
sbtn.area_map.render = lambda *args, **kwargs: None  # never fetch map tiles from tests


def catchment(cid, status, p_sens=1.0, load=None):
    return dict(catchment_id=cid, region="FI_SW", receiving_water_type="lake", ecological_status_class=status,
                catchment_area_km2=100.0, p_sensitivity=p_sens, monitored=bool(load), load=load)


SELECTION = sbtn.SelectionInput(
    globeId="g-1", name="test-selection",
    selected=[[[[22.0, 61.0], [22.1, 61.0], [22.1, 61.1], [22.0, 61.0]]]],
    # id, catchment, ha, buffer, drainage, soil, m to water, crop, P test, peat CO2e, farm, contract
    matches=[
        ["P1", "C1", 10.0, False, "open_ditch", "clay", 50, "pea", 12.0, 0.0, "F1", True],
        ["P2", "C1", 5.0, True, "subsurface", "organic", 40, "barley", None, 150.0, "F1", False],
        ["P3", "C2", 8.0, False, "subsurface", "clay", 80, "oats", 9.0, 0.0, "F2", False],
        ["P4", "C3", 2.0, True, "subsurface", "silt", 500, "wheat", 7.0, 0.0, "F3", False],
    ],
    crossed=[catchment("C1", "poor", 1.15, {"year": "2025", "total_p_load_kg": 900, "total_n_load_kg": 9000}),
             catchment("C9", "good")],
    related=[catchment("C1", "poor", 1.15, {"year": "2025", "total_p_load_kg": 900, "total_n_load_kg": 9000}),
             catchment("C2", "moderate"), catchment("C3", "good")],
)


class Assess(unittest.TestCase):
    def setUp(self):
        self.facts = sbtn.assess(SELECTION)
        self.by_id = {c["catchment"]: c for c in self.facts["catchments"]}

    def test_totals(self):
        self.assertEqual(self.facts["totals"], dict(parcels=4, farms=3, ha=25.0, contract_ha=10.0,
                                                    catchments_crossed=2, catchments_linked=3))

    def test_pressures_per_catchment(self):
        c1 = self.by_id["C1"]
        self.assertEqual((c1["runoff_risk_ha"], c1["open_ditch_ha"], c1["organic_ha"], c1["peat_co2e"]), (10.0, 10.0, 5.0, 150.0))
        self.assertEqual(c1["missing_p_tests"], 1)
        self.assertEqual(self.by_id["C2"]["runoff_risk_ha"], 8.0)  # 80 m, no buffer
        self.assertEqual(self.by_id["C3"]["runoff_risk_ha"], 0.0)  # 500 m, buffered

    def test_ranking_puts_high_pressure_poor_status_first(self):
        ranking = self.facts["ranking"]
        self.assertEqual([r["catchment"] for r in ranking], ["C1", "C2", "C3"])
        self.assertEqual(ranking[0]["tier"], "Priority")
        self.assertEqual(ranking[-1]["tier"], "Monitor")

    def test_ties_share_a_rank(self):
        rows = [dict(catchment=c, runoff_risk_ha=1.0, open_ditch_ha=0.0, status="poor", p_sensitivity=1.0) for c in "AB"]
        self.assertEqual({r["nature_rank"] for r in sbtn.rank(rows)}, {1})

    def test_crossed_catchment_without_parcels_is_listed(self):
        self.assertEqual(self.facts["crossed_without_parcels"], ["C9"])

    def test_water_pollution_screened_material(self):
        water = self.facts["screening"][0]
        self.assertEqual(water["status"], "Potentially material")


class Narrative(unittest.TestCase):
    def test_template_without_key(self):
        n = sbtn.build(SELECTION)["narrative"]
        self.assertEqual(n["source"], "template")
        self.assertIn("No LLM is configured", n["note"])

    def test_llm_text_and_unverified_figures(self):
        reply = dict(executive_summary="4 parcels cover 25 ha; C1 leads with 10 ha at risk and 9999 kg of something.",
                     materiality="m", pressures="p", prioritisation="r", data_gaps="g", next_steps=["a", "b", "c"])
        with mock.patch.object(llm, "provider", return_value="snowflake"), \
             mock.patch.object(llm, "label", return_value="Snowflake Cortex (test)"), \
             mock.patch.object(llm, "generate", return_value=reply) as generate:
            n = sbtn.build(SELECTION, {"reviewer": "R"})["narrative"]
        self.assertEqual((n["source"], n["writer"]), ("llm", "Snowflake Cortex (test)"))
        self.assertEqual(n["unverified"], ["9999"])
        prompt = generate.call_args.args[0]
        self.assertIn('"reviewer": "R"', prompt)
        self.assertIn("runoff_risk_ha", prompt)

    def test_llm_failure_falls_back(self):
        with mock.patch.object(llm, "provider", return_value="snowflake"), \
             mock.patch.object(llm, "generate", side_effect=llm.LLMUnavailable("Quota exceeded.")):
            n = sbtn.build(SELECTION)["narrative"]
        self.assertEqual(n["source"], "template")
        self.assertIn("Quota exceeded.", n["note"])


class Api(unittest.TestCase):
    def body(self):
        return {"selection": SELECTION.model_dump(), "review": {"reviewer": "R", "unknown_key": "ignored"}, "ai": False}

    def test_json(self):
        r = client.post("/sbtn/report", json=self.body()).json()
        self.assertEqual(r["facts"]["totals"]["parcels"], 4)
        self.assertEqual(r["review"], [{"label": "Reviewer", "value": "R"}])

    def test_html_from_form_post(self):
        import json
        res = client.post("/sbtn/report/html", data={"payload": json.dumps(self.body())})
        self.assertEqual(res.status_code, 200)
        self.assertIn("Step 2 · Prioritisation", res.text)
        self.assertIn("P1", res.text)

    def test_bad_payload_is_422(self):
        self.assertEqual(client.post("/sbtn/report/html", data={"payload": "not json"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
