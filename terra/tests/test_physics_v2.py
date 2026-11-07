import math
import time
import unittest
from unittest.mock import patch
from physics import Transport,land_step
from model import Model,MASK
from weather import Forecast,ANCHORS,VARIABLES,LAND_VARIABLES
from server import Engine

class ConservativeTransport(unittest.TestCase):
    def setUp(self):self.t=Transport([10.,11.,12.],[59.,60.,61.])
    def test_closed_mass_budget_and_nonnegative_with_cfl_substeps(self):
        q=[0.,0.,0.,0.,5.,0.,0.,0.,0.]
        new,b=self.t.advance(q,[100.]*9,[-60.]*9,10000)
        self.assertGreater(b['cfl_substeps'],1)
        self.assertGreaterEqual(min(new),0)
        self.assertLess(abs(b['residual_g_m'])/b['before_g_m'],1e-12)
    def test_open_boundary_budget(self):
        new,b=self.t.advance([2.]*9,[20.]*9,[0.]*9,3600,boundary=[4.]*9)
        self.assertGreater(b['boundary_exchange_g_m'],0)
        self.assertLess(abs(b['residual_g_m'])/b['before_g_m'],1e-12)
    def test_uniform_diffusion_has_no_effect(self):
        new,b=self.t.advance([3.]*9,[0.]*9,[0.]*9,3600)
        for value in new:self.assertAlmostEqual(value,3)

class LandWater(unittest.TestCase):
    def test_snow_captures_cold_precipitation_and_melts_when_warm(self):
        soil,snow,b=land_step(100,0,5,0,-8,-5,3600,450)
        self.assertEqual(soil,100);self.assertEqual(snow,5)
        new_soil,new_snow,b=land_step(soil,snow,0,0,8,3,3600,450)
        self.assertLess(new_snow,snow);self.assertGreater(new_soil,soil)
        self.assertAlmostEqual(b['residual_mm'],0,places=10)
    def test_extremes_conserve_soil_plus_snow(self):
        for soil in (0.,100.,450.):
            for temp in (-15,0,20):
                for rain in (0,500):
                    s,n,b=land_step(soil,30,rain,.8,temp,temp,3600,450)
                    self.assertTrue(0<=s<=450 and n>=0)
                    self.assertLess(abs(b['residual_mm']),1e-9)
    def test_frozen_soil_reduces_infiltration(self):
        frozen=land_step(100,0,10,0,5,-10,3600,450)[2]
        thawed=land_step(100,0,10,0,5,10,3600,450)[2]
        self.assertLess(frozen['infiltration_mm'],thawed['infiltration_mm'])
        self.assertGreater(frozen['runoff_mm'],thawed['runoff_mm'])

class RealInitialization(unittest.TestCase):
    def forecast(self):
        start=int(time.time()//3600)*3600;ts=[start+i*3600 for i in range(24)];records=[]
        for _ in ANCHORS:
            h={k:[1.]*24 for k in VARIABLES.split(',')};h.update(time=ts,temperature_2m=[-5.]*24,relative_humidity_2m=[75.]*24)
            for k in LAND_VARIABLES.split(','):h[k]=[.3 if k.startswith('soil_moisture') else .1 if k=='snow_depth' else -2.]*24
            records.append({'hourly':h})
        return Forecast(records=records,fetched=time.time())
    def test_depth_integrated_real_soil_and_snow(self):
        f=self.forecast();m=Model(time.time());m.initialize(f)
        self.assertEqual(m.initialization['soil_seeded_cells'],sum(MASK))
        for i,land in enumerate(MASK):
            if land:self.assertAlmostEqual(m.soil[i],300);self.assertAlmostEqual(m.snow[i],20)
        m.step(f.at(m.time+30),60)
        self.assertLess(abs(m.atmosphere_ledger['relative_residual']),1e-12)
        self.assertLess(abs(m.ledger['residual_mm']),1e-9)
    def test_precipitation_depletion_does_not_make_negative_vapor(self):
        f=Forecast();m=Model(time.time());m.initialize(f)
        forcing=f.at(m.time);forcing['precip_mm_h']=[1000.]*len(MASK)
        for _ in range(3):m.step(forcing,60)
        self.assertGreaterEqual(min(m.q),0)
        self.assertGreater(m.atmosphere_ledger['external_precipitation_water_kg'],0)
    def test_strict_live_startup_masks_placeholder_fields(self):
        e=Engine(require_live=True);s=e.snapshot()
        self.assertFalse(s['ready']);self.assertEqual(s['source']['mode'],'waiting')
        self.assertTrue(all(v is None for a in s['fields'].values() for v in a))
    def test_first_real_fetch_reseeds_and_reset_uses_api(self):
        f=self.forecast();e=Engine(require_live=True)
        with patch.object(Forecast,'fetch',return_value=f),patch.object(e.stop,'wait',return_value=True):e.refresh()
        self.assertTrue(e.snapshot()['ready'])
        self.assertEqual(e.model.initialization['kind'],'api_forecast')
        e.model.soil=[0.]*len(MASK)
        e.control({'reset':True})
        self.assertTrue(any(v>0 for v in e.model.soil))

if __name__=='__main__':unittest.main()
