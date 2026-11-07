import unittest
from datetime import datetime,timezone,timedelta
from agriculture import enrich
from weather import Forecast
from global_model import GlobalForecast,GLOBAL_MASK
from server import Engine
from test_history import fixture

class CropWeatherScreening(unittest.TestCase):
    def test_thresholds_and_daily_interval_totals(self):
        day=(datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat();f=fixture(Forecast,day)
        for r in f.records:
            r['hourly']['temperature_2m']=[-2.]*48;r['hourly']['wind_speed_10m']=[13.]*48
        fields=f.at(f.start+3600)
        self.assertTrue(all(abs(v-24)<1e-9 for v in fields['rain_day_mm']))
        self.assertTrue(all(v==24 for v in fields['rain_day_coverage_h']))
        self.assertTrue(all(v==100 for v in fields['frost_pct']))
        self.assertTrue(all(v==100 for v in fields['heavy_rain_pct']))
        self.assertTrue(all(v==100 for v in fields['wind_risk_pct']))
        self.assertTrue(all(v==0 for v in fields['heat_pct']))
    def test_incomplete_day_is_exposed_not_silently_called_complete(self):
        day=(datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat();f=fixture(Forecast,day)
        fields=f.at(f.start+86400+3600)
        self.assertTrue(all(v==23 for v in fields['rain_day_coverage_h']))
    def test_global_comparison_contains_coarse_land_mask_and_same_fields(self):
        today=datetime.now(timezone.utc).date();past=(today-timedelta(days=1)).isoformat()
        e=Engine(True);c=e.comparison;c.forecast=fixture(Forecast,past);c.global_forecast=fixture(GlobalForecast,past);c.date=past
        e.live_forecast=fixture(Forecast,today.isoformat());e.live_global_forecast=fixture(GlobalForecast,today.isoformat())
        f=c.frame(e.live_forecast.start+3600)
        self.assertTrue(f['global']['ready']);self.assertEqual(len(f['global']['grid']['land_mask']),648)
        self.assertEqual(len(f['global']['live']['frost_pct']),648)
        self.assertEqual(len(f['live']['frost_pct']),725)
        self.assertTrue(all(v==24 for v in f['difference']['rain_day_coverage_h']))
    def test_global_mask_has_land_and_sea(self):
        self.assertTrue(any(GLOBAL_MASK));self.assertTrue(any(not value for value in GLOBAL_MASK))

if __name__=='__main__':unittest.main()
