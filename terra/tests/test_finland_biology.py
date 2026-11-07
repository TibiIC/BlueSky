import json,math,unittest
from pathlib import Path
from biology.build_finland import summarize
from weather import Forecast,ANCHORS,LATS,LONS

class FinnishBiology(unittest.TestCase):
    def test_published_soil_subset(self):
        p=Path(__file__).resolve().parents[2]/'frontend/static/data/biology/karstula.json';d=json.loads(p.read_text())
        self.assertEqual(d['sample_count'],24);self.assertEqual(d['enzyme_record_count'],192)
        self.assertEqual({s['date'] for s in d['samples']},{'2021-09'})
        self.assertEqual({s['treatment'] for s in d['samples']},{'Control','N fertilization'})
        self.assertEqual(len({(s['lat'],s['lon']) for s in d['samples']}),1)
        self.assertEqual(d['license'],'CC BY 4.0')
    def test_nonfinite_measurements_rejected(self):
        som=b'code,Sample_type,Plot,BlockID,Replicate,Layer,Treatment,fungal_biomass_mg_g-1_DW,fungal_necromass_mg_g-1_DW,pH\nx,Soil,1,1,1,Organic layer,Control,nan,1,4\n'
        with self.assertRaises(ValueError):summarize(som,b'code,Enzyme,Value (nmol.h-1.g-1 DW)\n')

class BilinearWeather(unittest.TestCase):
    def test_regular_grid_reproduces_linear_field(self):
        f=Forecast();self.assertEqual(len(ANCHORS),195)
        for y in range(len(LATS)):
            for x in range(len(LONS)):
                weights=f.sparse_weights()[y*len(LONS)+x]
                self.assertLessEqual(len(weights),4);self.assertAlmostEqual(sum(w for i,w in weights),1)
                actual=sum(w*(ANCHORS[i][0]+2*ANCHORS[i][1]) for i,w in weights)
                self.assertAlmostEqual(actual,LATS[y]+2*LONS[x])
    def test_bilinear_values_stay_within_local_corner_range(self):
        f=Forecast()
        for weights in f.sparse_weights():
            values=[math.sin(i) for i,w in weights];value=sum(w*math.sin(i) for i,w in weights)
            self.assertTrue(min(values)-1e-12<=value<=max(values)+1e-12)
