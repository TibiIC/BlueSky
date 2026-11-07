import unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from server import Engine
from weather import Forecast
from test_history import fixture

class MatchedWeatherComparison(unittest.TestCase):
    def setUp(self):
        today=datetime.now(timezone.utc).date();self.day=(today-timedelta(days=1)).isoformat()
        self.engine=Engine(True);self.past=fixture(Forecast,self.day);self.live=fixture(Forecast,today.isoformat());self.live.product='forecast'
        for r in self.live.records:
            r['hourly']['temperature_2m']=[8.]*48;r['hourly']['precipitation']=[2.]*48;r['hourly']['wind_speed_10m']=[4.]*48
        self.engine.live_forecast=self.live
        self.c=self.engine.comparison;self.c.forecast=self.past;self.c.date=self.day
    def test_matched_utc_time_sign_units_and_weighted_values(self):
        now=self.live.start+12*3600+34*60+56
        f=self.c.frame(now)
        self.assertTrue(f['ready']);self.assertIn('12:34:56',f['historical_time'])
        self.assertEqual(f['units']['temp_c'],'°C')
        self.assertAlmostEqual(f['summary']['temp_c']['live'],8)
        self.assertAlmostEqual(f['summary']['temp_c']['historical'],5)
        self.assertAlmostEqual(f['summary']['temp_c']['difference'],3)
        self.assertAlmostEqual(f['summary']['precip_mm_h']['difference'],1)
        self.assertAlmostEqual(f['summary']['wind']['difference'],3)
        self.assertEqual(len(f['difference']['temp_c']),725)
    def test_comparison_does_not_modify_physics_clock_or_scenarios(self):
        clock=self.engine.model.time;soil=self.engine.model.soil[:]
        self.c.frame(self.live.start+3600)
        self.assertEqual(self.engine.model.time,clock);self.assertEqual(self.engine.model.soil,soil)
    def test_missing_or_expired_real_forecast_never_uses_synthetic(self):
        self.engine.live_forecast=Forecast();self.assertFalse(self.c.frame()['ready'])
        self.engine.live_forecast=self.live;self.assertFalse(self.c.frame(self.live.end+1)['ready'])
    def test_load_failure_retains_previous_reference(self):
        with patch.object(Forecast,'fetch_history',side_effect=ValueError('unavailable')):self.c.load('2000-01-01')
        self.assertIs(self.c.forecast,self.past);self.assertIn('unavailable',self.c.error)
    def test_unknown_parameters_rejected(self):
        with self.assertRaises(ValueError):self.c.select({'date':self.day,'scenario':2})

if __name__=='__main__':unittest.main()
