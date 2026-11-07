"""The evidence logic: competing explanations, confidence by level, decisive evidence, merging."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quality.evidence import confidence, explain  # noqa: E402
from quality.assess import decisive, merge, level_of  # noqa: E402
from quality.rules import Finding  # noqa: E402


class Explanations(unittest.TestCase):
    def test_exact_second_record_picks_the_mechanism(self):
        h = explain(39.616, 39616.0)  # ERP 39.616 "kg", shipment says 39.616 t
        self.assertEqual(h[0].mechanism, 'unit_x1000')
        self.assertLess(h[0].misfit, 0.001)
        self.assertEqual(confidence('B', h), 0.95)

    def test_no_mechanism_fits_discounts_confidence(self):
        h = explain(130.0, 100.0, {'unit_x1000', 'decimal_x10'})  # 30 % off: none of the slips explain it
        self.assertEqual(confidence('B', h), round(0.95 * 0.75, 3))

    def test_band_judges_variable_quantities_by_their_range(self):
        h = explain(85150.0, 50.0, {'unit_div1000'}, band=(2.0, 150.0))  # grams as kg; 85.15 kg is a normal top-up
        self.assertEqual(h[0].mechanism, 'unit_div1000')
        self.assertEqual(h[0].misfit, 0.0)


class Decisive(unittest.TestCase):
    def test_far_off_value_with_exact_power_of_ten_fix_is_decisive(self):
        self.assertTrue(decisive(explain(85150.0, 50.0, {'unit_div1000'}, band=(2.0, 150.0)), 'D'))

    def test_unit_slip_with_a_remaining_spike_passes_the_order_of_magnitude_test(self):
        self.assertTrue(decisive(explain(693108.5, 180.0, {'unit_x1000', 'unit_div1000'}), 'D'))  # -> 693, a spike remains

    def test_moderate_deviation_is_never_decisive(self):
        self.assertFalse(decisive(explain(1000.0, 100.0, {'decimal_div10'}), 'E'))  # 10x: could be a real big order


class Merging(unittest.TestCase):
    def test_second_record_and_history_merge_with_the_strongest_level(self):
        a = Finding('erp_purchase_lines', 'erp:1:10', 'unit_error', 2023, 'erp.unit_price', 'price 1000x', 0.95, 'correct', 'quantity', 39.616, 39616.0, {'index': 0, 'reference': 39616.0})
        b = Finding('erp_purchase_lines', 'erp:1:10', 'unit_error', 2023, 'erp.shipments', 'shipment 39.616 t', 0.95, 'correct', 'quantity', 39.616, 39616.0, {'index': 0, 'reference': 39616.0, 'level': 'B'})
        m = merge([a, b])
        self.assertEqual(len(m), 1)
        self.assertEqual(m[0].level, 'B')
        self.assertEqual([s['level'] for s in m[0].sources], ['B', 'E'])

    def test_no_shipment_supports_but_does_not_replace_a_duplicate(self):
        d = Finding('erp_purchase_lines', 'erp:2:10', 'duplicate_record', 2023, 'erp.duplicate', 'same posting', 0.9, 'drop', locator={'index': 1})
        s = Finding('erp_purchase_lines', 'erp:2:10', 'duplicate_record', 2023, 'erp.shipments', 'no shipment', 0.6, 'flag', locator={'index': 1, 'level': 'B', 'supporting': True})
        m = merge([d, s])
        self.assertEqual((m[0].action, m[0].level), ('drop', 'B'))
        self.assertEqual(level_of(d), 'D')


if __name__ == '__main__':
    unittest.main()
