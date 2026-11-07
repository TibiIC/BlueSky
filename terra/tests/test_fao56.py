import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from physics import land_step, water_stress, crop_coefficient, FIELD_CAPACITY_FRACTION, WILTING_FRACTION
from weather import Forecast, ANCHORS

CAP = 450.
FC = FIELD_CAPACITY_FRACTION * CAP
WP = WILTING_FRACTION * CAP


class FAO56(unittest.TestCase):
    def test_stress_limits(self):
        self.assertEqual(water_stress(FC, CAP), 1.)
        self.assertEqual(water_stress(CAP, CAP), 1.)
        self.assertEqual(water_stress(WP, CAP), 0.)
        self.assertEqual(water_stress(0., CAP), 0.)
        raw_edge = FC - .5 * (FC - WP)
        self.assertAlmostEqual(water_stress(raw_edge, CAP), 1.)
        self.assertAlmostEqual(water_stress((raw_edge + WP) / 2, CAP), .5)

    def test_transpiration_stops_at_wilting_point(self):
        soil = FC
        for _ in range(24 * 200):  # 200 dry days at 6 mm/day reference ET
            soil, _, b = land_step(soil, 0, 0, .25, 20, 15, 3600, CAP, kc=1.1)
            self.assertLess(abs(b['residual_mm']), 1e-9)
        self.assertGreaterEqual(soil, WP - 1e-9)
        self.assertLess(soil - WP, 1.)

    def test_kc_scales_et_when_unstressed(self):
        a = land_step(FC, 0, 0, .3, 20, 15, 3600, CAP, kc=.4)[2]['et_mm']
        b = land_step(FC, 0, 0, .3, 20, 15, 3600, CAP, kc=1.1)[2]['et_mm']
        self.assertAlmostEqual(b / a, 1.1 / .4)

    def test_crop_coefficient_shape(self):
        self.assertEqual(crop_coefficient(30, 60), .4)
        self.assertEqual(crop_coefficient(210, 60), 1.1)
        self.assertEqual(crop_coefficient(330, 60), .4)
        self.assertLess(crop_coefficient(170, 66), crop_coefficient(170, 56))


class TransportWind(unittest.TestCase):
    def records(self, with_850):
        ts = [i * 3600 for i in range(24)]
        out = []
        for _ in ANCHORS:
            h = dict(time=ts, temperature_2m=[10.] * 24, relative_humidity_2m=[70.] * 24, precipitation=[0.] * 24,
                     wind_speed_10m=[3.] * 24, wind_direction_10m=[270.] * 24, et0_fao_evapotranspiration=[.1] * 24)
            if with_850:
                h.update(wind_speed_850hPa=[12.] * 24, wind_direction_850hPa=[270.] * 24)
            out.append(dict(hourly=h))
        return out

    def test_uses_850_when_available(self):
        f = Forecast(start=0, records=self.records(True))
        x = f.at(3600)
        self.assertAlmostEqual(x['u_ms'][0], 3.)
        self.assertAlmostEqual(x['u_transport_ms'][0], 12.)
        self.assertEqual(f.transport_wind, '850hPa')

    def test_falls_back_to_10m(self):
        f = Forecast(start=0, records=self.records(False))
        x = f.at(3600)
        self.assertAlmostEqual(x['u_transport_ms'][0], 3.)
        self.assertEqual(f.transport_wind, '10m')


if __name__ == '__main__':
    unittest.main()

class ExtremeLandSteps(unittest.TestCase):
    def test_large_step_cannot_extract_below_wilting(self):
        soil,_,b=land_step(WP+1,0,0,100,30,20,86400,CAP,kc=2)
        self.assertGreaterEqual(soil,WP)
        self.assertLess(abs(b['residual_mm']),1e-9)
    def test_invalid_soil_parameters(self):
        for kw in ({'p':1},{'p':0},{'wilting_fraction':.8},{'capacity':0}):
            args=dict(soil=200,capacity=CAP);args.update(kw)
            with self.assertRaises(ValueError):water_stress(**args)
