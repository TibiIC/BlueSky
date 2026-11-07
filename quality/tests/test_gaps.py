"""Tests for the curation method (quality.gaps). Run: python3 -m unittest discover -s quality/tests -t ."""
import math
import unittest

import numpy as np

from quality import gaps
from quality.gaps import DECIMAL, T, UNIT, fitting_typos, flagged, issue_type, noise


class Noise(unittest.TestCase):
    def test_robust_to_a_few_typos(self):
        rng = np.random.default_rng(1)
        clean = rng.normal(0, 0.05, 500)
        dirty = np.concatenate([clean, [3.0] * 10])  # 2 % of the values are 1000x off
        self.assertAlmostEqual(noise(dirty), noise(clean), delta=0.01)

    def test_floor_for_exact_evidence(self):
        self.assertGreater(noise(np.zeros(50)), 0)


class Flag(unittest.TestCase):
    def test_needs_both_many_sigmas_and_a_real_ratio(self):
        self.assertTrue(flagged(3.0, 0.05))
        self.assertFalse(flagged(0.3, 0.05))   # 6 sigma, but only 2x off
        self.assertFalse(flagged(1.0, 0.3))    # 10x off, but within this series' natural spread


class Typos(unittest.TestCase):
    def test_grams_as_kg(self):
        # 85,150 kg against a usual 50 kg: only "divide by 1,000" explains it
        g = math.log10(85150 / 50.0)
        fits = fitting_typos(g, 0.1, UNIT)
        self.assertEqual([t[0] for t in fits], ['div1000'])

    def test_exact_evidence_needs_exact_fit(self):
        # tonnes typed as kg against the shipment record: exact
        self.assertEqual(fitting_typos(-3.0, 0.005, UNIT + DECIMAL)[0][0], 'mul1000')
        # 900x off is not a typo when the evidence is exact
        self.assertEqual(fitting_typos(math.log10(900), 0.005, UNIT + DECIMAL), [])

    def test_ten_and_krona_are_ambiguous_in_noisy_data(self):
        fits = fitting_typos(1.03, 0.05, [T['sek'], T['div10']])
        self.assertEqual(len(fits), 2)  # both fit: a person chooses

    def test_krona(self):
        fits = fitting_typos(math.log10(11.4), 0.01, [T['sek'], T['div10']])
        self.assertEqual([t[0] for t in fits], ['sek'])


class Labels(unittest.TestCase):
    def test_issue_types(self):
        self.assertEqual(issue_type('energy', T['div1000']), 'unit_error')
        self.assertEqual(issue_type('energy', None), 'meter_spike')
        self.assertEqual(issue_type('pcf', T['div1000']), 'pcf_unit_error')
        self.assertEqual(issue_type('spend', T['sek']), 'currency_error')
        self.assertEqual(issue_type('farm_n', T['div10']), 'decimal_shift')
        self.assertEqual(issue_type('farm_yield', T['div10']), 'outlier_implausible')


class Choice(unittest.TestCase):
    def item(self):
        return gaps.Item(key='k|f', series='energy', table='energy_meter_readings', record_key='k', year=2025, field='value', index=0,
                         unit='MWh', recorded=1000.0, expected=1.0, expected_from='', context='', gap=3.0, noise=0.01, status='fixed',
                         issue_type='unit_error', explanation='', default='div1000',
                         options=[{'id': 'div1000', 'value': 1.0}, {'id': 'expected', 'value': 1.0}, {'id': 'keep', 'value': 1000.0}])

    def test_default_until_a_person_decides(self):
        it = self.item()
        self.assertEqual(gaps.choice(it, {}), 'div1000')
        self.assertEqual(gaps.choice(it, {'k|f': 'keep'}), 'keep')
        self.assertEqual(gaps.choice(it, {'k|f': 'not-an-option'}), 'div1000')



class Units(unittest.TestCase):
    """A value in a different unit or currency is not a typo when the record says so."""

    def setUp(self):
        import pandas as pd
        self.pd = pd
        self._fx = gaps._fx
        gaps._fx = lambda raw: {'EUR': 1.0, 'SEK': 11.4, 'USD': 1.08}

    def tearDown(self):
        gaps._fx = self._fx

    def erp(self, rows):
        cols = ['doc_no', 'line_no', 'posting_date', 'uom', 'movement_type', 'quantity', 'net_amount', 'currency', 'material_text', 'supplier_id', 'material_id']
        return self.pd.DataFrame(rows, columns=cols)

    def test_tonnes_lines_compared_in_tonnes(self):
        raw = {'erp': self.erp([[1, 10, '2025-01-01', 'KG', 101, 39616.0, 1.0, 'EUR', 'x', 'S', 'M'],
                                [2, 10, '2025-01-01', 'TO', 101, 39.616, 1.0, 'EUR', 'x', 'S', 'M']]),
               'shipments': self.pd.DataFrame({'direction': ['inbound'] * 2, 'ref_doc': ['1', '2'], 't': [39.616, 39.616]})}
        d = gaps.s_purchases(raw)
        self.assertTrue(np.allclose(d.recorded.values, d.expected.values))  # 39,616 kg and 39.616 t both match

    def test_fuel_units_never_mixed(self):
        f = self.pd.DataFrame({'delivery_id': range(8), 'site_id': 'A', 'year': 2025,
                               'carrier': ['diesel'] * 4 + ['lng'] * 4, 'unit': ['l'] * 4 + ['t'] * 4,
                               'quantity': [10000, 11000, 9000, 10500, 20, 22, 18, 21]})
        d = gaps.s_fuel({'fuel_deliveries': f})
        self.assertTrue((np.abs(np.log10(d.recorded / d.expected)) < 0.1).all())

    def test_supplier_billing_in_two_currencies(self):
        rows = [[i, 10, '2025-01-01', 'EUR', 101, 0, 1000.0, 'EUR', 'x', 'S', 'M'] for i in range(5)]
        rows += [[9, 10, '2025-01-01', 'EUR', 101, 0, 11400.0, 'SEK', 'x', 'S', 'M']]  # the same 1,000 EUR, billed in krona
        d = gaps.s_spend({'erp': self.erp(rows)})
        sek = d[d.unit == 'SEK'].iloc[0]
        self.assertAlmostEqual(sek.recorded / sek.expected, 1.0)


if __name__ == '__main__':
    unittest.main()
