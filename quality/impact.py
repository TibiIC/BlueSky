"""How much each finding moves the inventory (t CO2e), with the package's own factors.

Used for materiality: which findings matter, how wide the inventory range is, and which checks
are worth an expert's time. Returns (scope, delta_t) where delta_t is the change in the
inventory if the finding's proposal is applied (for flags: if the flag turned out right).
These are first-order estimates; the inventory itself always comes from the reference calculator.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

WASTE_EF = {'anaerobic_digestion': 'EF-WASTE-BIO-AD', 'composting': 'EF-WASTE-BIO-COMPOST', 'incineration': 'EF-WASTE-MIXED-INC',
            'recycling': 'EF-WASTE-RECYCLE', 'landfill_codigestion': 'EF-WASTE-SPENTEARTH'}
FARM_EF = {'M100': 'EF-RAP-FI', 'M110': 'EF-VEG-PEA-FI', 'M111': 'EF-VEG-POT-FI', 'M112': 'EF-VEG-CAR-FI', 'M113': 'EF-VEG-SPI-FI', 'M114': 'EF-VEG-PEA-FI'}
CROP_MAT = {'turnip_rape': 'M100', 'pea': 'M110', 'potato': 'M111', 'carrot': 'M112', 'spinach': 'M113'}


class Context:
    def __init__(self, raw):
        from ccn_tools import factors as F
        self.F = F
        self.raw = raw
        self.lib = dict(zip(raw['ef_library'].ef_id, raw['ef_library'].kgco2e_per_unit))
        m = raw['materials'].set_index('material_id')
        self.mat_ef = {mid: self.lib.get(FARM_EF.get(mid, ef), 0.0) for mid, ef in m.default_ef_id.items()}
        self.mat_group = m.material_group.to_dict()
        self.country = raw['sites'].set_index('site_id').country.to_dict()
        e = raw['erp'].copy()
        e['year'] = e.posting_date.str[:4].astype(int)
        e['qty_kg'] = np.where(e.uom == 'TO', e.quantity * 1000, np.where(e.uom == 'KG', e.quantity, 0.0))
        self.deliveries = e[e.material_id.isin(set(CROP_MAT.values()))].groupby(['supplier_id', 'material_id', 'year']).qty_kg.sum()

    def row(self, table, f):
        i = f.locator.get('index')
        return None if i is None else self.raw[table].loc[i]


def _num(v):
    try:
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def impact(f, ctx: Context) -> tuple[str, float] | tuple[None, None]:
    F, obs, new = ctx.F, _num(f.observed), _num(f.proposed)
    t = f.table
    if t == 'erp_purchase_lines':
        r = ctx.row('erp', f)
        if r is None:
            return None, None
        ef = ctx.mat_ef.get(r.material_id, 0.0)
        spend = r.uom == 'EUR'
        scope = 'scope3:cat02' if ctx.mat_group.get(r.material_id) == 'capex' else 'scope3:cat01'
        if f.action == 'drop':
            amt = r.net_amount / F.FX_PER_EUR.get(r.currency, 1.0) if spend else (r.quantity * (1000 if r.uom == 'TO' else 1))
            return scope, -amt * ef / 1000
        if f.field == 'quantity' and obs is not None and new is not None and not spend:
            k = 1000 if r.uom == 'TO' else 1
            return scope, (new - obs) * k * ef / 1000
        if f.field == 'net_amount' and spend and obs is not None and new is not None:
            return scope, (new - obs) * ef / 1000
        if f.field == 'material_id':
            q = r.quantity * (1000 if r.uom == 'TO' else 1)
            return scope, q * (ctx.mat_ef.get(f.proposed, 0.0) - ef) / 1000
        if f.field == 'currency' and spend:
            fx_old, fx_new = F.FX_PER_EUR.get(f.observed, 1.0), F.FX_PER_EUR.get(f.proposed, 1.0)
            return scope, r.net_amount * (1 / fx_new - 1 / fx_old) * ef / 1000
        return scope, 0.0
    if t == 'energy_meter_readings':
        site, carrier, year = f.record_key.split(':')[1], f.record_key.split(':')[3], f.year
        d = (new or 0.0) - (obs or 0.0)
        if carrier == 'electricity':
            lb = (F.GRID_FI_LB if ctx.country.get(site, 'FI') == 'FI' else F.GRID_SE_LB).get(year, 0.03)
            return 'scope2_location', d * lb
        if carrier in ('district_heat', 'steam'):
            return 'scope2_location', d * F.HEAT_LB_EF.get(year, 0.12)
        return 'scope1', d * F.FUEL_EF_T_PER_MWH.get(carrier, 0.0)
    if t == 'fuel_deliveries':
        r = ctx.row('fuel_deliveries', f)
        ncv = {'lng': F.NCV['lng_t'], 'lpg': F.NCV['lpg_t'], 'light_fuel_oil': F.NCV['lfo_l'], 'diesel': F.NCV['diesel_l']}.get(r.carrier, 0)
        return 'scope1', ((new or 0) - (obs or 0)) * ncv * F.FUEL_EF_T_PER_MWH.get(r.carrier, 0.0)
    if t == 'refrigerant_service_log':
        r = ctx.row('refrigerants', f)
        if f.field == 'kg_added':
            return 'scope1', ((new or 0) - (obs or 0)) * F.REFRIGERANT_GWP.get(r.refrigerant, 0) / 1000
        if f.field == 'refrigerant':
            return 'scope1', r.kg_added * (F.REFRIGERANT_GWP.get(f.proposed, 0) - F.REFRIGERANT_GWP.get(f.observed, 0)) / 1000
    if t == 'goo_cancellations':
        r = ctx.row('goo', f)
        res = (F.RESIDUAL_FI if ctx.country.get(r.site_id, 'FI') == 'FI' else F.RESIDUAL_SE).get(f.year, 0.4)
        if f.field == 'vintage_year':  # the certificates start counting: covered MWh no longer at residual mix
            return 'scope2_market', -r.mwh_cancelled * res
        if f.field == 'mwh_cancelled':
            return 'scope2_market', -((new or 0) - (obs or 0)) * res
    if t == 'waste_transfer_notes':
        r = ctx.row('waste', f)
        ef = ctx.lib.get('EF-WASTE-PLASTIC-INC' if r.waste_stream == 'plastic_waste' else WASTE_EF.get(r.treatment, ''), 0.0)
        return 'scope3:cat05', ((new or 0) - (obs or 0)) / 1000 * ef / 1000
    if t == 'travel_bookings' and f.action == 'drop':
        r = ctx.row('travel', f)
        ef = ctx.lib.get('EF-PKM-FLIGHT-SHORT', 0.21) if r['mode'] == 'flight' else 0.01
        return 'scope3:cat06', -(r.pkm * ef + r.nights * ctx.lib.get('EF-HOTEL-NIGHT', 12)) / 1000
    if t == 'shipments' and f.action == 'add':
        ef_id = f.record_key.split(':')[2]
        return 'scope3:cat04', (new or 0) * ctx.lib.get(ef_id, 0.0) / 1000
    if t == 'supplier_pcfs':
        sup, mat, year = f.record_key.split(':')[1:4]
        e = ctx.raw['erp']
        kg = e[(e.supplier_id == sup) & (e.material_id == mat) & (e.posting_date.str[:4] == year)]
        q = float(np.where(kg.uom == 'TO', kg.quantity * 1000, kg.quantity).sum())
        pc = ctx.raw['pcfs']
        v = pc[(pc.supplier_id == sup) & (pc.material_id == mat) & (pc.year == int(year))].value
        return 'scope3:cat01', q * (ctx.mat_ef.get(mat, 0.0) - (float(v.iloc[0]) if len(v) else 0.0)) / 1000
    if t == 'farm_survey':
        return farm_impact(f, ctx)
    return None, None


def farm_impact(f, ctx: Context):
    """Contract-farm emissions = delivered kg x footprint per kg; the footprint per kg is the
    per-ha footprint / yield. Area does not enter (it only matters for nutrient models)."""
    from ccn_tools.farm_calculator import farm_footprint_per_ha
    r = ctx.row('farm_survey', f)
    if r is None:
        return None, None
    mat = CROP_MAT.get(r.crop)
    kg = float(ctx.deliveries.get((r.farm_id, mat, int(r.year)), 0.0))
    if not kg:
        return 'scope3:cat01', 0.0
    base = pd.DataFrame([r]).assign(organic_soil=r.soil_type_reported.lower().startswith('organic'))

    def per_kg(df):
        return float(farm_footprint_per_ha(df)[0]) / (float(df.yield_t_ha.iloc[0]) * 1000)

    before = per_kg(base)
    if f.issue_type == 'soil_misreport':
        share = f.locator.get('organic_share', 0.0)
        after = per_kg(base.assign(organic_soil=False)) * (1 - share) + per_kg(base.assign(organic_soil=True)) * share
    elif f.field in ('yield_t_ha', 'n_mineral_kg_ha') and _num(f.proposed) is not None:
        after = per_kg(base.assign(**{f.field: float(f.proposed)}))
    else:
        return 'scope3:cat01', 0.0
    return 'scope3:cat01', kg * (after - before) / 1000
