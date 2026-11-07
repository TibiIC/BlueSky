import json
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
from http.server import ThreadingHTTPServer
from model import NX,NY,Model,advect,bucket
from weather import Forecast,ANCHORS,VARIABLES
from server import Engine,Handler

class Physics(unittest.TestCase):
    def test_advection_constant_and_direction(self):
        n=NX*NY
        self.assertEqual(advect([4.]*n,[10.]*n,[0.]*n,60),[4.]*n)
        q=[float(i) for j in range(NY) for i in range(NX)]
        out=advect(q,[10.]*n,[0.]*n,600)
        self.assertLess(out[14*NX+12],q[14*NX+12])
        self.assertGreaterEqual(min(out),min(q));self.assertLessEqual(max(out),max(q))
    def test_bucket_conservation_extremes(self):
        for s in (0.,10.,149.,150.):
            for p in (0,1,500):
                for et in (0,.3,100):
                    new,r,e,run,d=bucket(s,p,et,3600,150)
                    self.assertAlmostEqual(new-s,r-e-run-d,places=10)
                    self.assertTrue(0<=new<=150)
    def test_long_run_horizon_and_finite(self):
        f=Forecast(start=time.time());m=Model(f.start);m.speed=3600
        for _ in range(30):m.advance(f,1)
        frame=m.frame(f.meta())
        self.assertAlmostEqual(m.time-f.start,30*3600,places=4)
        self.assertLess(abs(frame['water_budget_mean_land_mm']['residual_mm']),1e-10)
        json.dumps(frame,allow_nan=False)
        m.time=f.end-10;m.advance(f,1);self.assertEqual(m.time,f.end)
    def test_api_validation_wind_and_intervals(self):
        ts=[1700000000+i*3600 for i in range(24)];records=[]
        for _ in ANCHORS:
            h={k:[1.]*24 for k in VARIABLES.split(',')};h.update(time=ts,temperature_2m=[10.]*24,relative_humidity_2m=[75.]*24,wind_direction_10m=[359.,1.]+[0.]*22,wind_speed_10m=[10.]*24,precipitation=list(range(24)))
            records.append({'hourly':h})
        Forecast.validate(records);f=Forecast(records=records,fetched=time.time());a=f.at(ts[0]+1800)
        self.assertAlmostEqual(a['u_ms'][0],0,places=10);self.assertLess(a['v_ms'][0],-9.9)
        self.assertAlmostEqual(a['precip_mm_h'][0],1)
        records[0]['hourly']['temperature_2m'][0]=None
        with self.assertRaises(ValueError):Forecast.validate(records)
    def test_failure_retains_forecast(self):
        engine=Engine();old=engine.forecast
        with patch.object(Forecast,'fetch',side_effect=ValueError('bad upstream')),patch.object(engine.stop,'wait',return_value=True):engine.refresh()
        self.assertIs(engine.forecast,old);self.assertIn('bad upstream',engine.error)
class HTTP(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine=Engine(True);cls.http=ThreadingHTTPServer(('127.0.0.1',0),Handler);cls.http.daemon_threads=True;cls.http.engine=cls.engine
        cls.url='http://127.0.0.1:'+str(cls.http.server_port)
        threading.Thread(target=cls.http.serve_forever,daemon=True).start()
    @classmethod
    def tearDownClass(cls):cls.engine.stop.set();cls.http.shutdown();cls.http.server_close()
    def get(self,path):return urllib.request.urlopen(self.url+path,timeout=4)
    def post(self,data):return urllib.request.urlopen(urllib.request.Request(self.url+'/api/control',data=json.dumps(data).encode(),headers={'Content-Type':'application/json'}),timeout=4)
    def test_assets_and_frame(self):
        for path in ('/','/app.js','/style.css','/api/health','/api/geography','/api/global-frame'):
            with self.get(path) as r:self.assertEqual(r.status,200)
        with self.get('/api/frame') as r:f=json.load(r)
        self.assertEqual(len(f['fields']['soil_mm']),725);self.assertEqual(f['source']['mode'],'synthetic')
    def test_controls_atomic_validation_pause_reset(self):
        with self.post({'paused':True,'speed':1200}) as r:self.assertTrue(json.load(r)['controls']['paused'])
        now=self.engine.model.time;self.engine.model.advance(self.engine.forecast,1);self.assertEqual(now,self.engine.model.time)
        with self.assertRaises(urllib.error.HTTPError):self.post({'speed':4,'capacity_mm':0})
        self.assertEqual(self.engine.model.speed,1200)
        with self.post({'reset':True}) as r:self.assertEqual(json.load(r)['controls']['speed'],1)
    def test_sse_multiple_frames_and_disconnect(self):
        with self.get('/events') as r:
            self.assertEqual(r.headers['Content-Type'],'text/event-stream')
            for _ in range(2):
                self.assertTrue(r.readline().startswith(b'id:'))
                self.assertEqual(r.readline(),b'event: frame\n')
                payload=json.loads(r.readline().decode()[6:]);self.assertEqual(payload['schema'],'terra.frame.v1')
                self.assertEqual(r.readline(),b'\n')
        with self.get('/api/health') as r:self.assertTrue(json.load(r)['ok'])

class GlobalPhysics(unittest.TestCase):
    def test_periodic_dateline_and_boundedness(self):
        from global_model import GX,GY,global_advect
        n=GX*GY;q=[0.]*n
        for j in range(GY):q[j*GX+GX-1]=1
        out=global_advect(q,[100.]*n,[0.]*n,3600)
        self.assertGreater(out[(GY//2)*GX],0)
        self.assertTrue(all(0<=v<=1 for v in out))
        self.assertEqual(global_advect([2.]*n,[100.]*n,[0.]*n,300),[2.]*n)
    def test_global_forecast_model_and_grid(self):
        from global_model import GlobalForecast,GlobalModel
        f=GlobalForecast(start=time.time());m=GlobalModel(f.start)
        m.advance_to(f.start+3600,f);a=m.frame(f)
        self.assertEqual(len(a['fields']['moisture_g_m3']),612)
        self.assertTrue(a['grid']['periodic_longitude'])
        self.assertNotIn('soil_mm',a['fields'])
        json.dumps(a,allow_nan=False)

if __name__=='__main__':unittest.main()
