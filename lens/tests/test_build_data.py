"""Tests for the warming-level fit in lens/build_data.py (no package data needed)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import build_data as B  # noqa: E402


def synthetic_climate(slope: float) -> dict:
    """One cell whose indicators rise exactly `slope` per °C of global warming."""
    def ind(g):
        v = 10 + slope * (g - B.GWL_BASELINE)
        return {k: v for k in B.FIT_INDICATORS}
    periods = {'baseline': ind(B.GWL_BASELINE)}
    for d, c in B.DECADE_CENTRES.items():
        periods[d] = {s: ind(B.gwl_at(s, c)) for s in B.SCENARIOS}
    return {'indicators': {'X': {'periods': periods}}}


class GwlTest(unittest.TestCase):
    def test_matches_ar6_period_centres(self):
        self.assertAlmostEqual(B.gwl_at('ssp245', 2050.5), 2.0)
        self.assertAlmostEqual(B.gwl_at('ssp585', 2090.5), 4.4)
        self.assertAlmostEqual(B.gwl_at('ssp126', 2005.5), B.GWL_BASELINE)

    def test_ordering_by_scenario(self):
        for c in B.DECADE_CENTRES.values():
            self.assertLessEqual(B.gwl_at('ssp126', c), B.gwl_at('ssp245', c))
            self.assertLessEqual(B.gwl_at('ssp245', c), B.gwl_at('ssp585', c))


class FitTest(unittest.TestCase):
    def test_recovers_exact_slope(self):
        w = B.build_warming(synthetic_climate(4.0))
        fit = w['cells']['X']['hotDaysJJ']
        self.assertAlmostEqual(fit['slope'], 4.0, places=3)
        self.assertAlmostEqual(fit['r2'], 1.0, places=2)
        self.assertAlmostEqual(fit['base'], 10.0)

    def test_flat_indicator_has_zero_slope(self):
        w = B.build_warming(synthetic_climate(0.0))
        self.assertAlmostEqual(w['cells']['X']['gdd5']['slope'], 0.0)

    def test_publishes_gwl_table(self):
        w = B.build_warming(synthetic_climate(1.0))
        self.assertEqual(set(w['gwl']), set(B.SCENARIOS))
        self.assertLess(w['gwl']['ssp126']['2050s'], w['gwl']['ssp585']['2050s'])


if __name__ == '__main__':
    unittest.main()
