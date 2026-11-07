import json,math,unittest
from pathlib import Path
from research.build_decision_data import metrics
class DecisionEvidence(unittest.TestCase):
    def test_bias_rmse(self):
        m=metrics([(1,0),(3,1)]);self.assertEqual(m['bias_mm'],1.5);self.assertAlmostEqual(m['rmse_mm'],math.sqrt(2.5))
        with self.assertRaises(ValueError):metrics([])
    def test_real_reference_coverage_and_provenance(self):
        d=json.loads((Path(__file__).resolve().parents[2]/'frontend/static/data/decision/evidence.json').read_text())
        self.assertEqual(len(d['climate']['members']),8)
        self.assertEqual(len(d['climate']['models']),2)
        for r in d['benchmark']['results']:
            self.assertEqual(r['days'],183);self.assertEqual(r['series'][0]['date'],'2018-04-01');self.assertEqual(r['series'][-1]['date'],'2018-09-30');self.assertLess(r['max_water_residual_mm'],1e-9)
        self.assertIn('not independent',d['benchmark']['notice'])
        self.assertIn('synthetic',d['supply']['notice'])
