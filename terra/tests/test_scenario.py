import unittest
from weather import Forecast
from scenario import run

class ScenarioTests(unittest.TestCase):
    def test_identity_and_budget(self):
        f=Forecast();r=run(f,f.start,dict(warming_c=0,rain_factor=1,et_factor=1,hours=2))
        for row in r['series']:
            for v in row['regions'].values():self.assertEqual(v['baseline'],v['scenario'])
        self.assertLess(r['max_water_residual_mm'],1e-10)
        self.assertEqual(len(r['series']),3)
    def test_invalid(self):
        f=Forecast()
        for p in ({'warming_c':float('nan')},{'rain_factor':-1},{'hours':True},{'unknown':1}):
            with self.assertRaises(ValueError):run(f,f.start,p)
    def test_sensitivity_and_no_mutation(self):
        f=Forecast();before=f.at(f.start)['temp_c'][:]
        r=run(f,f.start,dict(warming_c=8,rain_factor=0,et_factor=2,hours=6))
        self.assertEqual(before,f.at(f.start)['temp_c'])
        self.assertNotEqual(r['series'][-1]['regions']['Nordic land']['baseline'],r['series'][-1]['regions']['Nordic land']['scenario'])
