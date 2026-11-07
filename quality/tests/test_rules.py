"""Each rule on small synthetic tables: it must catch the planted error, propose the exact
correction, and leave the legitimate look-alikes alone. No package data needed.

    python3 -m unittest discover -s quality/tests -v
"""
import sys
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from quality import rules as R  # noqa: E402

FX = {'EUR': 1.0, 'SEK': 11.4, 'USD': 1.08}
R._fx = lambda raw: FX  # the package's exchange rates, without importing the package


def run(fn, raw):
    checked = []
    return fn(raw, checked), checked


def erp_rows(rows):
    base = dict(line_no=10, company_code='C100', plant='S-SAK', uom='KG', currency='EUR', origin_country='FI',
                lot_id=None, movement_type=101, reference_doc=None, wbs_element=None, material_text='x')
    return pd.DataFrame([{**base, **r} for r in rows])


class ErpRules(unittest.TestCase):
    def test_unit_price_tonnes_as_kg_and_decimal_shift(self):
        rows = [dict(doc_no=str(i), posting_date='2025-03-01', material_id='M1', supplier_id='S', quantity=1000.0, net_amount=500.0) for i in range(10)]
        rows += [dict(doc_no='T', posting_date='2025-03-02', material_id='M1', supplier_id='S', quantity=1.0, net_amount=500.0),    # tonnes keyed as kg
                 dict(doc_no='D', posting_date='2025-03-03', material_id='M1', supplier_id='S', quantity=10000.0, net_amount=500.0),  # extra digit
                 dict(doc_no='V', posting_date='2025-03-04', material_id='M1', supplier_id='S', quantity=1.0, net_amount=500.0, uom='TO'),  # vessel lot: legit
                 dict(doc_no='C', posting_date='2025-03-05', material_id='M1', supplier_id='S', quantity=-1000.0, net_amount=-500.0, movement_type=122)]  # credit note
        out, checked = run(R.erp_unit_price, {'erp': erp_rows(rows)})
        by = {f.record_key: f for f in out}
        self.assertEqual(by['erp:T:10'].issue_type, 'unit_error')
        self.assertEqual(by['erp:T:10'].proposed, 1000.0)
        self.assertEqual(by['erp:D:10'].issue_type, 'decimal_shift')
        self.assertEqual(by['erp:D:10'].proposed, 1000.0)
        self.assertNotIn('erp:V:10', by, 'vessel lots in tonnes are converted, not flagged')
        self.assertNotIn('erp:C:10', by, 'credit notes are legitimate')
        self.assertTrue(any('Credit note' in c.reason for c in checked))

    def test_duplicate_posting_flags_the_later_one(self):
        rows = [dict(doc_no='A', posting_date='2025-05-01', material_id='M1', supplier_id='S', quantity=100.0, net_amount=50.0),
                dict(doc_no='B', posting_date='2025-05-04', material_id='M1', supplier_id='S', quantity=100.0, net_amount=50.0),
                dict(doc_no='C', posting_date='2025-09-01', material_id='M1', supplier_id='S', quantity=100.0, net_amount=50.0)]  # months later: a new order
        out, _ = run(R.erp_duplicate, {'erp': erp_rows(rows)})
        self.assertEqual([f.record_key for f in out], ['erp:B:10'])
        self.assertEqual(out[0].action, 'drop')

    def test_material_text_names_another_material(self):
        mats = pd.DataFrame({'material_id': ['M1', 'M2'], 'erp_name': ['Herne', 'Porkkana']})
        rows = [dict(doc_no='A', posting_date='2025-01-01', material_id='M1', supplier_id='S', quantity=1.0, net_amount=1.0, material_text='Porkkana')]
        out, _ = run(R.erp_material_text, {'erp': erp_rows(rows), 'materials': mats})
        self.assertEqual((out[0].issue_type, out[0].proposed), ('material_mismatch', 'M2'))

    def test_sek_spend_booked_as_eur(self):
        rows = [dict(doc_no=str(i), posting_date='2025-02-01', material_id='SVC', supplier_id='S', quantity=0.0, uom='EUR', net_amount=10000.0) for i in range(6)]
        rows.append(dict(doc_no='X', posting_date='2025-02-02', material_id='SVC', supplier_id='S', quantity=0.0, uom='EUR', net_amount=114000.0))
        out, _ = run(R.erp_currency, {'erp': erp_rows(rows)})
        f = [f for f in out if f.record_key == 'erp:X:10'][0]
        self.assertEqual((f.issue_type, f.field, f.proposed), ('currency_error', 'net_amount', 10000.0))

    def test_capex_reconciles_against_the_register(self):
        rows = [dict(doc_no='A', posting_date='2024-03-01', material_id='CAP', supplier_id='S', quantity=0.0, uom='EUR', net_amount=500000.0, wbs_element='Line'),
                dict(doc_no='B', posting_date='2024-04-01', material_id='CAP', supplier_id='S', quantity=0.0, uom='EUR', net_amount=5700000.0, wbs_element='Line')]
        capex = pd.DataFrame({'year': [2024], 'project': ['Line'], 'capex_eur': [1000000.0]})
        out, _ = run(R.erp_capex, {'erp': erp_rows(rows), 'capex': capex})
        self.assertEqual((out[0].record_key, out[0].proposed), ('erp:B:10', 500000.0))


class EnergyRules(unittest.TestCase):
    def meters(self):
        rows = []
        for y in range(2019, 2026):
            for m in range(1, 13):
                rows.append(dict(site_id='S-SAK', year=y, month=m, carrier='electricity', unit='MWh',
                                 value=2600.0 if m in (7, 8, 9) else 1500.0))  # harvest campaign every year
        return pd.DataFrame(rows)

    def test_seasonal_peak_is_not_an_error(self):
        out, checked = run(R.energy_meter, {'energy_meter': self.meters()})
        self.assertEqual(out, [])
        self.assertTrue(any('Seasonal peak' in c.reason for c in checked))

    def test_kwh_in_mwh_column_plus_spike_on_the_same_reading(self):
        em = self.meters()
        i = em[(em.year == 2024) & (em.month == 11)].index[0]
        em.loc[i, 'value'] = 6_000_000.0  # kWh in the MWh column, and 4x too high after the fix
        out, _ = run(R.energy_meter, {'energy_meter': em})
        types = sorted(f.issue_type for f in out if f.record_key == 'energy:S-SAK:2024-11:electricity')
        self.assertEqual(types, ['meter_spike', 'unit_error'])
        spike = [f for f in out if f.issue_type == 'meter_spike'][0]
        self.assertAlmostEqual(spike.proposed, 1500.0, places=3)

    def test_missing_month_is_estimated_not_silently_zero(self):
        em = self.meters()
        em = em.drop(em[(em.year == 2023) & (em.month == 5)].index)
        out, _ = run(R.energy_meter, {'energy_meter': em})
        f = out[0]
        self.assertEqual((f.issue_type, f.action, f.proposed), ('missing_record', 'add', 1500.0))


class RefrigerantAndCertificates(unittest.TestCase):
    def test_grams_wrong_gas_and_genuine_ammonia(self):
        rows = [dict(site_id='S', system='Cold store', refrigerant='R404A', year=2019 + k, service_date='x', reason='leak', event_id=f'E{k}', kg_added=80.0) for k in range(5)]
        rows += [dict(site_id='S', system='Cold store', refrigerant='R404A', year=2024, service_date='x', reason='leak', event_id='G', kg_added=27750.0),  # grams
                 dict(site_id='S', system='Cold store', refrigerant='R717_ammonia', year=2023, service_date='x', reason='leak', event_id='W', kg_added=120.0),  # wrong code
                 dict(site_id='S', system='Freezer', refrigerant='R717_ammonia', year=2023, service_date='x', reason='leak', event_id='N', kg_added=55.0),  # real ammonia
                 dict(site_id='S', system='Freezer', refrigerant='R717_ammonia', year=2024, service_date='x', reason='leak', event_id='N2', kg_added=60.0)]
        out, checked = run(R.refrigerant_log, {'refrigerants': pd.DataFrame(rows)})
        by = {(f.record_key, f.issue_type): f for f in out}
        self.assertEqual(by[('refrigerant:G', 'unit_error')].proposed, 27.75)
        self.assertEqual(by[('refrigerant:W', 'wrong_gas_code')].proposed, 'R404A')
        self.assertFalse(any(k[0].startswith('refrigerant:N') for k in by), 'a genuine ammonia system is not an error')
        self.assertTrue(any('Ammonia' in c.reason for c in checked))

    def test_guarantees_of_origin_follow_the_registry(self):
        goo = pd.DataFrame([dict(year=2025, site_id='S-PUD', mwh_cancelled=2200.0, technology='wind', production_country='FI', vintage_year=2023),
                            dict(year=2025, site_id='S-BJU', mwh_cancelled=4460.0, technology='hydro', production_country='SE', vintage_year=2025)])
        reg = pd.DataFrame([dict(consumption_year=2025, beneficiary_site='S-PUD', mwh=2200.0),
                            dict(consumption_year=2025, beneficiary_site='S-BJU', mwh=372.0)])
        out, _ = run(R.goo_registry, {'goo': goo, 'goo_registry': reg})
        got = {(f.record_key, f.field): f.proposed for f in out}
        self.assertEqual(got[('goo:S-PUD:2025', 'vintage_year')], 2025)
        self.assertEqual(got[('goo:S-BJU:2025', 'mwh_cancelled')], 372.0)


class OtherRules(unittest.TestCase):
    def test_travel_duplicate_uses_the_organisers_definition(self):
        t = pd.DataFrame([dict(year=2025, traveller_id='E1', travel_date='2025-01-03', mode='flight', route='HEL-AMS', pkm=3000.0, nights=1, booking_id='B1'),
                          dict(year=2025, traveller_id='E1', travel_date='2025-01-03', mode='flight', route='HEL-AMS', pkm=3000.0, nights=1, booking_id='B2'),
                          dict(year=2025, traveller_id='E1', travel_date='2025-01-03', mode='flight', route='HEL-AMS', pkm=3000.0, nights=2, booking_id='B3')])
        out, _ = run(R.travel_duplicate, {'travel': t})
        self.assertEqual([f.record_key for f in out], ['travel:B2'])

    def test_commuting_labels_and_distance(self):
        c = pd.DataFrame([dict(response_id='C1', site_id='S', one_way_km=12.0, mode='henkilöauto', days_on_site_per_week=5, shift_worker=False),
                          dict(response_id='C2', site_id='S', one_way_km=37600.0, mode='bike_walk', days_on_site_per_week=5, shift_worker=False),
                          dict(response_id='C3', site_id='S', one_way_km=8.0, mode='train', days_on_site_per_week=5, shift_worker=False)])
        out, _ = run(R.commuting_survey, {'commuting': c})
        got = {(f.record_key, f.issue_type): f.proposed for f in out}
        self.assertEqual(got, {('commute:C1', 'mode_mislabel'): 'car', ('commute:C2', 'unit_error'): 37.6})

    def test_swapped_coordinates(self):
        fr = pd.DataFrame([dict(farm_id='F1', lat=21.94, lon=61.11), dict(farm_id='F2', lat=61.0, lon=22.5)])
        out, _ = run(R.farm_coordinates, {'farm_registry': fr})
        self.assertEqual((out[0].record_key, out[0].proposed), ('farm:F1', [61.11, 21.94]))

    def test_supplier_pcf_period_and_unit(self):
        pcfs = pd.DataFrame([dict(file='a', supplier_id='S', material_id='M1', year=2024, value=1.30, declared_unit='kilogram', ref_start='2024-01-01', ref_end='2025-01-01'),
                             dict(file='b', supplier_id='S', material_id='M1', year=2025, value=1409.1, declared_unit='kilogram', ref_start='2025-01-01', ref_end='2026-01-01'),
                             dict(file='c', supplier_id='T', material_id='M1', year=2025, value=1.20, declared_unit='kilogram', ref_start='2022-01-01', ref_end='2023-01-01')])
        mats = pd.DataFrame({'material_id': ['M1'], 'default_ef_id': ['EF1'], 'erp_name': ['x']})
        lib = pd.DataFrame({'ef_id': ['EF1'], 'kgco2e_per_unit': [1.3]})
        out, _ = run(R.pcf_validity, {'pcfs': pcfs, 'materials': mats, 'ef_library': lib})
        got = {(f.record_key, f.issue_type) for f in out}
        self.assertEqual(got, {('pcf:S:M1:2025', 'pcf_unit_error'), ('pcf:T:M1:2025', 'pcf_stale_period')})


if __name__ == '__main__':
    unittest.main()
