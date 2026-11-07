import math,unittest
from hydrology.routing import Router
from model import Model,NX,NY
from weather import Forecast
class Routing(unittest.TestCase):
 def network(self):return {'basins':[dict(id=1,next_down=2,cells=[[0,1]],modeled_area_km2=1),dict(id=2,next_down=0,cells=[[1,1]],modeled_area_km2=1)]}
 def test_conservation_downstream_delay_and_pause(self):
  r=Router([1e6,1e6],[True,True],self.network());r.advance([1,0],3600)
  self.assertGreater(r.flows[1],0);self.assertGreater(r.flows[2],0);self.assertLess(r.flows[2],r.flows[1]);self.assertAlmostEqual(r.budget['residual_m3'],0,places=8)
  initial=sum(r.storage.values());old=r.storage.copy();r.advance([1,0],0);self.assertEqual(old,r.storage)
  for _ in range(48):r.advance([0,0],3600);self.assertAlmostEqual(r.budget['residual_m3'],0,places=8)
  self.assertLess(sum(r.storage.values()),initial*.01)
 def test_cycle_rejected(self):
  n=self.network();n['basins'][1]['next_down']=1
  with self.assertRaises(ValueError):Router([1e6]*2,[True]*2,n)
class RainMotion(unittest.TestCase):
 def test_rain_proxy_advects_and_pause_freezes_state(self):
  f=Forecast();m=Model(f.start);m.initialize(f);a=m.rain_pattern[:]
  m.speed=600;m.advance(f,1)
  self.assertNotEqual(a,m.rain_pattern);self.assertTrue(all(v>=0 and math.isfinite(v) for v in m.rain_pattern));self.assertLess(abs(m.rain_pattern_budget['residual_g_m']),1)
  m.paused=True;before=m.rain_pattern[:];clock=m.time;m.advance(f,1);self.assertEqual(before,m.rain_pattern);self.assertEqual(clock,m.time)
 def test_land_still_uses_forecast_rain(self):
  f=Forecast();m=Model(f.start);m.initialize(f);forcing=f.at(f.start);forcing['precip_mm_h']=[0.]*(NX*NY);m.rain_pattern=[10.]*(NX*NY);m.step(forcing,60)
  self.assertEqual(m.ledger['precip_mm'],0)
