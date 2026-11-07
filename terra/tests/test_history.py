import copy
import time
import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from weather import Forecast,VARIABLES,LAND_VARIABLES
from global_model import GlobalForecast
from server import Engine
from history import summarize

def fixture(cls,start):
    beginning=datetime.fromisoformat(start).replace(tzinfo=timezone.utc).timestamp()
    records=[]
    for _ in cls.anchors:
        h={k:[1.]*48 for k in VARIABLES.split(',')}
        h.update(time=[beginning+i*3600 for i in range(48)],temperature_2m=[5.]*48,relative_humidity_2m=[70.]*48)
        for k in LAND_VARIABLES.split(','):h[k]=[.25 if k.startswith('soil_moisture') else 0.]*48
        records.append({'hourly':h})
    f=cls(start=beginning,records=records,fetched=time.time());f.end=beginning+86400;f.product='reanalysis';f.history_range=[start,start]
    return f

class HistoricalReplay(unittest.TestCase):
    start=(datetime.now(timezone.utc).date()-timedelta(days=14)).isoformat()
    def test_date_validation_blocks_future_and_unbounded_requests(self):
        with self.assertRaises(ValueError):Forecast.history_dates('1950-01-01','1950-01-09')
        with self.assertRaises(ValueError):Forecast.history_dates('1940-01-01','1940-01-01')
        with self.assertRaises(ValueError):Forecast.history_dates('2999-01-01','2999-01-01')
        self.assertEqual(Forecast.history_dates(self.start,self.start)[0].isoformat(),self.start)
    def test_selecting_active_live_mode_does_not_reset_state(self):
        e=Engine(True);model=e.model;clock=model.time
        e.set_timeline({'mode':'live'})
        self.assertIs(e.model,model);self.assertEqual(e.model.time,clock)
    def test_summary_uses_hourly_interval_rain_and_land_means(self):
        f=fixture(Forecast,self.start);e=Engine(True);s=summarize(f,e.model)
        self.assertEqual(len(s['series']),24)
        self.assertEqual(s['precipitation_total_mm'],24)
        self.assertEqual(s['min_mean_temperature_c'],5)
    def test_switch_restart_and_return_to_live(self):
        f=fixture(Forecast,self.start);g=fixture(GlobalForecast,self.start);e=Engine(True)
        original=e.forecast;e.history_request=1
        with patch.object(Forecast,'fetch_history',return_value=f),patch.object(GlobalForecast,'fetch_history',return_value=g):e.load_history(self.start,self.start,1)
        self.assertEqual(e.mode,'historical');self.assertEqual(e.model.time,f.start)
        self.assertEqual(e.model.initialization['kind'],'api_reanalysis')
        self.assertEqual(e.snapshot()['source']['forcing_kind'],'weather_reanalysis')
        e.model.time+=3600;e.control({'reset':True});self.assertEqual(e.model.time,f.start)
        e.set_timeline({'mode':'live'});self.assertEqual(e.mode,'live');self.assertIs(e.forecast,original)
        self.assertLess(abs(e.model.time-time.time()),2)
    def test_failed_or_cancelled_load_does_not_replace_active_model(self):
        e=Engine(True);old=e.model;e.history_request=1;e.history_loading=True
        with patch.object(Forecast,'fetch_history',side_effect=ValueError('archive unavailable')):e.load_history(self.start,self.start,1)
        self.assertIs(e.model,old);self.assertIn('archive unavailable',e.history_error)
        f=fixture(Forecast,self.start);g=fixture(GlobalForecast,self.start)
        e.history_request=2
        with patch.object(Forecast,'fetch_history',return_value=f),patch.object(GlobalForecast,'fetch_history',return_value=g):e.load_history(self.start,self.start,1)
        self.assertIs(e.model,old)
    def test_background_live_refresh_does_not_overwrite_archive(self):
        e=Engine(True);historical=fixture(Forecast,self.start);e.forecast=historical;e.mode='historical'
        live=Forecast()
        with patch.object(Forecast,'fetch',return_value=live),patch.object(e.stop,'wait',return_value=True):e.refresh()
        self.assertIs(e.forecast,historical);self.assertIs(e.live_forecast,live)

if __name__=='__main__':unittest.main()
