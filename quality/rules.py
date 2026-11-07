"""Data-quality rules: one documented detector per error type.

Every detector returns Finding rows. A finding says what looks wrong, why (rule + evidence),
how sure we are, and what we propose: `correct` (change a field), `drop` (remove a duplicate),
`add` (fill a missing record with a stated estimate) or `flag` (needs a human; no automatic change).

Rules find, code corrects, a human approves. Nothing here changes the raw data: the pipeline
applies approved corrections to a copy, so every number can be rebuilt from raw + corrections.

Legitimate oddities the organisers planted as traps (credit notes, vessel lots in tonnes,
seasonal harvest peaks, ammonia systems) are recorded as `Checked` rows, so the review shows
what was looked at and deliberately left alone.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field as dc_field
from typing import Any, Callable

import numpy as np
import pandas as pd

# Raw table name (as used in record keys) -> key in ccn_tools.io.load_raw()
TABLES = {
    'erp_purchase_lines': 'erp', 'energy_meter_readings': 'energy_meter', 'fuel_deliveries': 'fuel_deliveries',
    'goo_cancellations': 'goo', 'refrigerant_service_log': 'refrigerants', 'waste_transfer_notes': 'waste',
    'travel_bookings': 'travel', 'commuting_survey': 'commuting', 'shipments': 'shipments',
    'farm_survey': 'farm_survey', 'farm_registry': 'farm_registry', 'supplier_pcfs': 'pcfs',
}


@dataclass
class Finding:
    table: str
    record_key: str
    issue_type: str
    year: int
    rule: str
    evidence: str
    confidence: float
    action: str  # correct | drop | add | flag
    field: str | None = None
    observed: Any = None
    proposed: Any = None
    locator: dict = dc_field(default_factory=dict)  # how to find the row; 'reference' = the evidence value compared against
    # Filled in by quality.assess:
    level: str = ''                                   # strongest evidence level (A–G)
    sources: list = dc_field(default_factory=list)    # Evidence rows, strongest first
    hypotheses: list = dc_field(default_factory=list) # competing explanations, best first
    impact_tco2e: float | None = None                 # inventory change if applied
    status: str = ''                                  # confirmed | proposed | needs_review | unexplained
    priority: float = 0.0                             # review order: |impact| x (1 - confidence)
    ai: dict | None = None                            # model contributions, labelled as such

    def row(self) -> dict:
        d = asdict(self)
        for k in ('observed', 'proposed'):
            v = d[k]
            if isinstance(v, (np.floating, np.integer)):
                d[k] = v.item()
        return d


@dataclass
class Checked:
    """A legitimate oddity that looks like an error and was deliberately not flagged."""
    table: str
    record_key: str
    year: int
    reason: str


RULES: list[tuple[str, Callable]] = []


def rule(name: str):
    def deco(fn):
        RULES.append((name, fn))
        fn.rule_name = name
        return fn
    return deco


def _erp(raw):
    e = raw['erp'].copy()
    e['year'] = e.posting_date.str[:4].astype(int)
    e['key'] = 'erp:' + e.doc_no.astype(str) + ':' + e.line_no.astype(str)
    e['qty_kg'] = np.where(e.uom == 'TO', e.quantity * 1000, np.where(e.uom == 'KG', e.quantity, np.nan))
    return e


def _fx(raw):
    from ccn_tools import factors as F
    return F.FX_PER_EUR


# ------------------------------------------------------------------ ERP purchases

@rule('erp.unit_price')
def erp_unit_price(raw, checked):
    """Unit price vs the material's median: ~1000x high = tonnes keyed as kg; ~10x high = quantity
    divided by 10; ~10x low = an extra digit (decimal shift). Credit notes and vessel lots (uom TO)
    are converted first, so they are never mistaken for errors."""
    e = _erp(raw)
    eur = e.net_amount / e.currency.map(_fx(raw)).fillna(1.0)
    goods = e[(e.uom != 'EUR') & (e.movement_type == 101) & (e.qty_kg > 0)].copy()
    goods['price'] = eur[goods.index] / goods.qty_kg
    goods['ratio'] = goods.price / goods.groupby('material_id').price.transform('median')
    out = []
    for i, r in goods.iterrows():
        q = r.quantity
        if r.ratio > 300:
            out.append(Finding('erp_purchase_lines', r.key, 'unit_error', r.year, 'erp.unit_price',
                               f'Unit price {r.ratio:.0f}x the {r.material_id} median: tonnes keyed with uom KG.',
                               0.95, 'correct', 'quantity', q, round(q * 1000, 3), {'index': int(i), 'reference': round(q / r.ratio, 3)}))
        elif 0.07 < r.ratio < 0.14:
            out.append(Finding('erp_purchase_lines', r.key, 'decimal_shift', r.year, 'erp.unit_price',
                               f'Unit price {r.ratio:.2f}x the median: quantity has one digit too many.',
                               0.85, 'correct', 'quantity', q, round(q / 10, 3), {'index': int(i), 'reference': round(q / r.ratio, 3)}))
        elif 7 < r.ratio < 14:
            out.append(Finding('erp_purchase_lines', r.key, 'decimal_shift', r.year, 'erp.unit_price',
                               f'Unit price {r.ratio:.1f}x the median: quantity is missing a digit.',
                               0.8, 'correct', 'quantity', q, round(q * 10, 3), {'index': int(i), 'reference': round(q / r.ratio, 3)}))
        elif r.ratio > 4 or r.ratio < 0.25:
            out.append(Finding('erp_purchase_lines', r.key, 'outlier_implausible', r.year, 'erp.unit_price',
                               f'Unit price {r.ratio:.2f}x the {r.material_id} median, outside the bands of known slips.',
                               0.4, 'flag', 'quantity', q, None, {'index': int(i), 'reference': round(q / r.ratio, 3), 'unexplained': True}))
    for i, r in e[e.movement_type == 122].iterrows():
        checked.append(Checked('erp_purchase_lines', r.key, int(r.year), 'Credit note (movement 122): a legitimate return that nets against the receipt.'))
    n_to = int((e.uom == 'TO').sum())
    if n_to:
        checked.append(Checked('erp_purchase_lines', f'{n_to} vessel lots', 0, 'Vessel lots in tonnes (uom TO): converted to kg, not an error.'))
    return out


@rule('erp.material_text')
def erp_material_text(raw, checked):
    """The line's material text names a different material than its material_id."""
    e = _erp(raw)
    m = raw['materials'].set_index('erp_name').material_id
    out = []
    for i, r in e.iterrows():
        named = m.get(r.material_text)
        if isinstance(named, str) and named != r.material_id:
            out.append(Finding('erp_purchase_lines', r.key, 'material_mismatch', r.year, 'erp.material_text',
                               f'Text "{r.material_text}" is material {named}, but the line says {r.material_id}.',
                               0.9, 'correct', 'material_id', r.material_id, named, {'index': int(i)}))
    return out


@rule('erp.currency')
def erp_currency(raw, checked):
    """A line in a different currency from everything else the supplier invoices."""
    e = _erp(raw)
    usual = e.groupby('supplier_id').currency.agg(lambda s: s.value_counts().index[0])
    share = e.groupby('supplier_id').currency.agg(lambda s: s.value_counts(normalize=True).iloc[0])
    out = []
    for i, r in e.iterrows():
        u = usual[r.supplier_id]
        if r.currency != u and share[r.supplier_id] >= 0.8:
            out.append(Finding('erp_purchase_lines', r.key, 'currency_error', r.year, 'erp.currency',
                               f'Supplier {r.supplier_id} invoices in {u} ({share[r.supplier_id]:.0%} of lines); this line says {r.currency}.',
                               0.85, 'correct', 'currency', r.currency, u, {'index': int(i)}))
    # Spend lines (uom EUR) about 11.4x the supplier's usual size: a SEK amount booked as EUR.
    sek = _fx(raw)['SEK']
    sp = e[(e.uom == 'EUR') & (e.movement_type == 101)].copy()
    sp['ratio'] = sp.net_amount / sp.groupby('supplier_id').net_amount.transform('median')
    for i, r in sp[(sp.ratio > sek * 0.7) & (sp.ratio < sek * 1.4) & (sp.currency == 'EUR')].iterrows():
        out.append(Finding('erp_purchase_lines', r.key, 'currency_error', r.year, 'erp.currency',
                           f'Amount {r.ratio:.1f}x the supplier median, matching the SEK rate ({sek}): a SEK amount booked as EUR.',
                           0.8, 'correct', 'net_amount', r.net_amount, round(r.net_amount / sek, 2), {'index': int(i), 'reference': round(r.net_amount / r.ratio, 2)}))
    for i, r in sp[(sp.ratio > 50) | (sp.ratio < 0.02)].iterrows():
        out.append(Finding('erp_purchase_lines', r.key, 'currency_error', r.year, 'erp.currency',
                           f'Spend {r.ratio:.0f}x the supplier median: amount keyed in the wrong unit or currency.',
                           0.6, 'flag', 'net_amount', r.net_amount, None, {'index': int(i)}))
    return out


@rule('erp.duplicate')
def erp_duplicate(raw, checked):
    """Same supplier, material, quantity and amount posted again within 14 days: a duplicate posting.
    The later posting is the duplicate."""
    e = _erp(raw)
    e = e[e.movement_type == 101].copy()
    e['date'] = pd.to_datetime(e.posting_date)
    out = []
    for _, g in e.groupby(['supplier_id', 'material_id', 'quantity', 'net_amount']):
        if len(g) < 2:
            continue
        g = g.sort_values(['date', 'doc_no'])
        first = g.iloc[0]
        for i, r in g.iloc[1:].iterrows():
            if (r.date - first.date).days <= 14:
                out.append(Finding('erp_purchase_lines', r.key, 'duplicate_record', r.year, 'erp.duplicate',
                                   f'Same supplier, material, quantity and amount as {first.key} ({(r.date - first.date).days} days earlier).',
                                   0.9, 'drop', locator={'index': int(i)}))
    return out


@rule('erp.shipments')
def erp_shipments(raw, checked):
    """Independent second record: every inbound shipment leg states the tonnes it carried for an
    ERP document. The ERP quantity must equal the shipment's tonnes (level B evidence). A mismatch
    is repaired to the shipment's value, and the mechanism (x1000, x10, ...) is identified.
    A goods receipt with no shipment at all is evidence of a duplicate posting."""
    e = _erp(raw)
    sh = raw['shipments']
    legs = sh[sh.direction == 'inbound'].copy()
    legs['ref_doc'] = legs.ref_doc.astype(str)
    t = legs.groupby('ref_doc').t.median()
    goods = e[(e.uom != 'EUR') & (e.movement_type == 101)].copy()
    goods['ship_kg'] = goods.doc_no.astype(str).map(t) * 1000
    out = []
    for i, r in goods[goods.ship_kg.notna()].iterrows():
        if abs(r.qty_kg / r.ship_kg - 1) <= 0.01:
            continue
        ref = r.ship_kg if r.uom == 'KG' else r.ship_kg / 1000  # in the line's own unit
        f = r.ship_kg / r.qty_kg
        itype = 'unit_error' if f > 300 or f < 1 / 300 else 'decimal_shift'
        out.append(Finding('erp_purchase_lines', r.key, itype, r.year, 'erp.shipments',
                           f'ERP says {r.quantity:,.3f} {r.uom}; the shipment for this document carried {r.ship_kg / 1000:,.3f} t.',
                           0.95, 'correct', 'quantity', r.quantity, round(ref, 3), {'index': int(i), 'reference': round(ref, 3), 'level': 'B'}))
    for i, r in goods[goods.ship_kg.isna()].iterrows():
        out.append(Finding('erp_purchase_lines', r.key, 'duplicate_record', r.year, 'erp.shipments',
                           f'No shipment carried goods for document {r.doc_no}: a receipt without a delivery.',
                           0.6, 'flag', locator={'index': int(i), 'level': 'B', 'supporting': True}))
    return out


@rule('erp.capex')
def erp_capex(raw, checked):
    """ERP capex lines (WBS element) must add up to the capex register for that project and year.
    When they exceed it, a line whose amount divided by the SEK rate makes the totals match is a
    SEK amount booked as EUR."""
    e = _erp(raw)
    reg = raw['capex'].groupby(['year', 'project']).capex_eur.sum()
    sek = _fx(raw)['SEK']
    out = []
    lines = e[e.wbs_element.notna() & (e.movement_type == 101)]
    for (year, wbs), g in lines.groupby(['year', 'wbs_element']):
        target = reg.get((year, wbs))
        if target is None:
            continue
        total = g.net_amount.sum()
        if total <= target * 1.05:
            continue
        # The line whose SEK->EUR conversion brings the total closest to the register.
        gap = ((total - g.net_amount + g.net_amount / sek) - target).abs()
        i = gap.idxmin()
        if gap[i] <= 0.05 * target:
            r = g.loc[i]
            fixed = total - r.net_amount + r.net_amount / sek
            out.append(Finding('erp_purchase_lines', r.key, 'currency_error', int(year), 'erp.capex',
                               f'"{wbs}" {year}: ERP lines total {total:,.0f} but the capex register says {target:,.0f}; '
                               f'this line divided by the SEK rate brings the total to {fixed:,.0f} ({gap[i] / target:.1%} off).',
                               0.9, 'correct', 'net_amount', r.net_amount, round(r.net_amount / sek, 2), {'index': int(i), 'reference': round(target - (total - r.net_amount), 2)}))
        else:
            out.append(Finding('erp_purchase_lines', f'capex:{year}:{wbs}', 'total_mismatch', int(year), 'erp.capex',
                               f'"{wbs}" {year}: ERP lines total {total:,.0f} vs the capex register {target:,.0f}.', 0.6, 'flag'))
    return out


# ------------------------------------------------------------------ Energy meters

@rule('energy.meter')
def energy_meter(raw, checked):
    """Per site and carrier: a month ~1000x the typical month is kWh in the MWh column. After that
    fix, a month far above the same month in other years is a spike (both can hit one reading).
    High months that recur every year (the July–September pea campaign at Säkylä) are seasonal,
    not errors. Missing months, and spikes, are replaced by the same month in other years scaled
    to this year's level (sites grow and shrink)."""
    em = raw['energy_meter'].copy()
    out = []
    for (site, carrier), g in em.groupby(['site_id', 'carrier']):
        med = g.value.median()
        unit = g.value > 200 * med if med > 0 else pd.Series(False, index=g.index)
        v = g.value.where(~unit, g.value / 1000)  # unit-fixed values
        same_month = v.groupby(g.month).median()
        ratio = (v / g.month.map(same_month)).groupby(g.year).median()  # this year's level vs typical

        level = (v / g.month.map(same_month))
        by_ym = dict(zip(zip(g.year, g.month), level))
        bad = set(zip(g.year[v > 2.5 * g.month.map(same_month)], g.month[v > 2.5 * g.month.map(same_month)]))

        def estimate(year, month):
            """Same-month typical value x the level of the neighbouring months that year
            (falls back to the year's level, then 1)."""
            near = [by_ym[(year, m)] for m in (month - 1, month + 1) if (year, m) in by_ym and (year, m) not in bad]
            f = float(np.mean(near)) if near else float(ratio.get(year, 1.0))
            return float(same_month.get(month, med) * f)

        for i, r in g.iterrows():
            key = f'energy:{site}:{int(r.year)}-{int(r.month):02d}:{carrier}'
            val = v[i]
            if unit[i]:
                out.append(Finding('energy_meter_readings', key, 'unit_error', int(r.year), 'energy.meter',
                                   f'{r.value:,.0f} vs a typical {med:,.0f} MWh/month: kWh reported in the MWh column.',
                                   0.95, 'correct', 'value', r.value, round(val, 3), {'index': int(i), 'reference': float(same_month.get(r.month, med))}))
            ref = same_month.get(r.month, med)
            if ref > 0 and val > 2.5 * ref:
                est = estimate(int(r.year), r.month)
                # observed = the value after any unit fix, so impacts are not double-counted
                out.append(Finding('energy_meter_readings', key, 'meter_spike', int(r.year), 'energy.meter',
                                   f'{val:,.1f} MWh is {val / ref:.1f}x the same month in other years; replaced by {est:,.1f}.',
                                   0.8, 'correct', 'value', round(float(val), 3), round(est, 3), {'index': int(i), 'reference': round(est, 3)}))
            elif med > 0 and val > 1.4 * med and ref > 1.4 * med:
                checked.append(Checked('energy_meter_readings', key, int(r.year), f'Seasonal peak: this month is high every year ({ref:,.0f} MWh typical).'))
        for year, gy in g.groupby('year'):
            if len(gy) >= 8:
                for m in sorted(set(range(1, 13)) - set(gy.month)):
                    est = estimate(int(year), m)
                    out.append(Finding('energy_meter_readings', f'energy:{site}:{int(year)}-{m:02d}:{carrier}', 'missing_record', int(year),
                                       'energy.meter', f'Month {m} missing from {year}; estimated {est:,.1f} MWh from the same month in other years, scaled to the neighbouring months.',
                                       0.8, 'add', 'value', None, round(est, 3),
                                       {'row': {'site_id': site, 'year': int(year), 'month': m, 'carrier': carrier, 'value': round(est, 3), 'unit': 'MWh'}}))
    return out


@rule('fuel.units')
def fuel_units(raw, checked):
    """Litre-based fuels with a delivery ~1000x smaller than usual: m3 keyed as litres."""
    fd = raw['fuel_deliveries']
    out = []
    for (carrier, unit), g in fd.groupby(['carrier', 'unit']):
        med = g.quantity.median()
        ok = g.quantity[(g.quantity >= med / 30) & (g.quantity <= med * 30)]  # robust: other slips can't widen it
        band = (float(ok.min()), float(ok.max()))  # the carrier's observed delivery range
        for i, r in g[g.quantity < med / 200].iterrows():
            out.append(Finding('fuel_deliveries', f'fuel:{r.delivery_id}', 'unit_error', int(r.year), 'fuel.units',
                               f'{r.quantity} {unit} vs a typical {med:,.0f}: m3 keyed as litres.' if unit == 'l' else f'{r.quantity} {unit} vs a typical {med:,.1f}: unit slip.',
                               0.9, 'correct', 'quantity', r.quantity, round(r.quantity * 1000, 3), {'index': int(i), 'reference': float(med), 'band': band}))
    return out


@rule('waste.units')
def waste_units(raw, checked):
    """A waste note ~1000x below the stream's usual monthly quantity: tonnes keyed as kg."""
    w = raw['waste']
    out = []
    for (site, stream), g in w.groupby(['site_id', 'waste_stream']):
        med = g.quantity.median()
        ok = g.quantity[(g.quantity >= med / 30) & (g.quantity <= med * 30)]  # robust: other slips can't widen it
        band = (float(ok.min()), float(ok.max()))  # the stream's observed range, slips excluded
        for i, r in g[g.quantity < med / 200].iterrows():
            out.append(Finding('waste_transfer_notes', f'waste:{r.transfer_note}', 'unit_error', int(r.year), 'waste.units',
                               f'{r.quantity} kg vs a typical {med:,.0f} kg for {stream}: tonnes keyed as kg.',
                               0.9, 'correct', 'quantity', r.quantity, round(r.quantity * 1000, 3), {'index': int(i), 'reference': float(med), 'band': band}))
    return out


# ------------------------------------------------------------------ Refrigerants and certificates

@rule('refrigerant.log')
def refrigerant_log(raw, checked):
    """kg_added ~1000x the system's usual top-up = grams; a gas code that differs from the gas the
    system uses in most (>= 60 %) of its events = wrong code (e.g. an R404A cold store logged as
    ammonia). Genuine ammonia (R717) systems are legitimate and have GWP 0."""
    r = raw['refrigerants']
    out = []
    for (site, system), g in r.groupby(['site_id', 'system']):
        med = g.kg_added.median()
        ok = g.kg_added[(g.kg_added <= 30 * med) & (g.kg_added >= med / 30)]  # robust: other slips can't widen it
        band = (float(ok.min()), float(ok.max()))  # the system's observed top-up range
        gas = g.refrigerant.value_counts()
        for i, x in g.iterrows():
            key = f'refrigerant:{x.event_id}'
            if med > 0 and x.kg_added > 200 * med:
                out.append(Finding('refrigerant_service_log', key, 'unit_error', int(x.year), 'refrigerant.log',
                                   f'{x.kg_added:,.0f} kg vs a typical {med:,.1f} kg top-up on {system}: grams in the kg column.',
                                   0.95, 'correct', 'kg_added', x.kg_added, round(x.kg_added / 1000, 3), {'index': int(i), 'reference': float(med), 'band': band}))
            dominant_share = gas.iloc[0] / gas.sum()
            if x.refrigerant != gas.index[0] and dominant_share >= 0.6 and gas.iloc[0] >= 3:
                out.append(Finding('refrigerant_service_log', key, 'wrong_gas_code', int(x.year), 'refrigerant.log',
                                   f'{system} uses {gas.index[0]} in {gas.iloc[0]} of {gas.sum()} events; this one says {x.refrigerant}.',
                                   0.85, 'correct', 'refrigerant', x.refrigerant, gas.index[0], {'index': int(i)}))
            elif x.refrigerant.startswith('R717'):
                checked.append(Checked('refrigerant_service_log', key, int(x.year), 'Ammonia (R717) top-up: a safety matter, not a CO2e emission (GWP 0).'))
    return out


@rule('goo.registry')
def goo_registry(raw, checked):
    """The internal GoO log is checked against the national registry statement (authoritative):
    vintage must equal the consumption year, and cancelled MWh must match the registry."""
    g, reg = raw['goo'], raw['goo_registry']
    tot = reg.groupby(['consumption_year', 'beneficiary_site']).mwh.sum()
    out = []
    for i, r in g.iterrows():
        key = f'goo:{r.site_id}:{int(r.year)}'
        if r.vintage_year != r.year and (int(r.year), r.site_id) in tot.index:
            out.append(Finding('goo_cancellations', key, 'certificate_mismatch', int(r.year), 'goo.registry',
                               f'Vintage {r.vintage_year} ≠ consumption year {r.year}; the registry shows {r.year} production.',
                               0.9, 'correct', 'vintage_year', int(r.vintage_year), int(r.year), {'index': int(i)}))
        reg_mwh = tot.get((int(r.year), r.site_id))
        if reg_mwh is not None and abs(r.mwh_cancelled - reg_mwh) > max(1.0, 0.01 * reg_mwh):
            out.append(Finding('goo_cancellations', key, 'certificate_mismatch', int(r.year), 'goo.registry',
                               f'Log says {r.mwh_cancelled:,.0f} MWh; the registry statement shows {reg_mwh:,.0f} MWh.',
                               0.9, 'correct', 'mwh_cancelled', r.mwh_cancelled, round(float(reg_mwh), 3), {'index': int(i), 'reference': float(reg_mwh)}))
    return out


# ------------------------------------------------------------------ Travel, commuting, shipments

@rule('travel.duplicate')
def travel_duplicate(raw, checked):
    """The organisers' definition: same traveller, date, route, distance and nights as an earlier
    row in the file; flag the later row(s)."""
    t = raw['travel']
    dup = t[t.duplicated(['traveller_id', 'travel_date', 'route', 'pkm', 'nights'], keep='first')]
    return [Finding('travel_bookings', f'travel:{r.booking_id}', 'duplicate_record', int(r.year), 'travel.duplicate',
                    'Same traveller, date, route, distance and nights as an earlier row: re-imported booking.',
                    0.95, 'drop', locator={'index': int(i)}) for i, r in dup.iterrows()]


MODE_ALIASES = {'car': 'car', 'auto': 'car', 'henkilöauto': 'car', 'linja-auto': 'bus', 'bus': 'bus', 'ev_car': 'ev_car',
                'carpool': 'carpool', 'train': 'train', 'bike_walk': 'bike_walk'}


@rule('commuting.survey')
def commuting_survey(raw, checked):
    """Mode labels outside the survey's code list (Finnish words, capitals) are mapped to codes;
    one-way distances over 1,000 km are metres keyed as km."""
    c = raw['commuting']
    out = []
    for i, r in c.iterrows():
        key = f'commute:{r.response_id}'
        mode = str(r['mode'])
        code = MODE_ALIASES.get(mode.lower())
        if mode not in MODE_ALIASES or code != mode:
            out.append(Finding('commuting_survey', key, 'mode_mislabel', 2025, 'commuting.survey',
                               f'Mode "{mode}" is not a survey code; maps to "{code}".' if code else f'Mode "{mode}" is not a survey code.',
                               0.8 if code else 0.5, 'correct' if code else 'flag', 'mode', mode, code, {'index': int(i)}))
        if r.one_way_km > 1000:
            out.append(Finding('commuting_survey', key, 'unit_error', 2025, 'commuting.survey',
                               f'{r.one_way_km:,.0f} km one way: metres keyed as km.',
                               0.9, 'correct', 'one_way_km', r.one_way_km, round(r.one_way_km / 1000, 2), {'index': int(i), 'reference': float(c.one_way_km[c.one_way_km < 1000].median())}))
    return out


@rule('shipments.legs')
def shipments_legs(raw, checked):
    """Every import lot from overseas has a road leg plus a sea or Ro-Pax leg. A lot whose
    supplier's other lots always include a sea leg, but this one has none, is missing a leg;
    its tonne-km is estimated from that supplier's other lots."""
    e = _erp(raw)
    sh = raw['shipments']
    inb = sh[sh.direction == 'inbound'].copy()
    inb['ref_doc'] = inb.ref_doc.astype(str)
    legs = inb.groupby('ref_doc').ef_id.apply(set)
    sea = {'EF-TKM-SHIP-BULK', 'EF-TKM-SHIP-REEFER', 'EF-TKM-ROPAX'}
    imp = e[(e.origin_country != 'FI') & (e.uom != 'EUR') & (e.movement_type == 101)].copy()
    imp['legs'] = imp.doc_no.astype(str).map(legs)
    imp = imp[imp.legs.notna()]
    out = []
    for sup, g in imp.groupby('supplier_id'):
        sea_sets = [s & sea for s in g.legs]
        with_sea = [s for s in sea_sets if s]
        if len(with_sea) < 3 or len(with_sea) / len(g) < 0.7:
            continue
        mode = pd.Series([next(iter(s)) for s in with_sea]).value_counts().index[0]
        km = inb[(inb.ref_doc.isin(g.doc_no.astype(str))) & (inb.ef_id == mode)]
        km_per_t = float((km.tkm / km.t).median()) if len(km) else np.nan
        for _, r in g[[not s for s in sea_sets]].iterrows():
            est = round(km_per_t * (r.qty_kg / 1000), 2) if np.isfinite(km_per_t) else None
            out.append(Finding('shipments', f'ship:{r.doc_no}:{mode}', 'missing_leg', r.year, 'shipments.legs',
                               f'{sup} lots normally include a {mode} leg ({len(with_sea)}/{len(g)}); lot {r.doc_no} has none. Estimated {km_per_t:,.0f} km.',
                               0.75, 'add', 'tkm', None, est,
                               {'row': {'year': int(r.year), 'direction': 'inbound', 'ref_doc': str(r.doc_no), 'ef_id': mode,
                                        'mode': mode.replace('EF-TKM-', '').lower(), 't': round(r.qty_kg / 1000, 3),
                                        'km': round(km_per_t, 1) if np.isfinite(km_per_t) else None, 'tkm': est}}))
    return out


# ------------------------------------------------------------------ Farms

@rule('farm.survey')
def farm_survey(raw, checked):
    """Survey answers checked against the parcel register and each crop's normal ranges:
    area vs declared parcels; yields and mineral N ~10x outside the crop's range (decimal slip)."""
    sv, h, p = raw['farm_survey'], raw['crop_history'], raw['parcels']
    area = h.merge(p[['parcel_id', 'area_ha']], on='parcel_id').groupby(['farm_id', 'crop', 'year']).area_ha.sum()
    med_y = sv.groupby('crop').yield_t_ha.median()
    med_n = sv[sv.n_mineral_kg_ha > 0].groupby('crop').n_mineral_kg_ha.median()
    out = []
    for i, r in sv.iterrows():
        key = f'farm_survey:{r.survey_id}'
        a = area.get((r.farm_id, r.crop, r.year))
        if a and abs(r.area_ha - a) / a > 0.25:
            out.append(Finding('farm_survey', key, 'area_mismatch', int(r.year), 'farm.survey',
                               f'Reports {r.area_ha} ha of {r.crop}; declared parcels total {a:.2f} ha.',
                               0.85, 'correct', 'area_ha', r.area_ha, round(float(a), 2), {'index': int(i), 'reference': float(a)}))
        my = med_y.get(r.crop)
        if my and r.yield_t_ha > 5 * my:
            out.append(Finding('farm_survey', key, 'outlier_implausible', int(r.year), 'farm.survey',
                               f'Yield {r.yield_t_ha} t/ha is {r.yield_t_ha / my:.0f}x the {r.crop} median: decimal slip.',
                               0.85, 'correct', 'yield_t_ha', r.yield_t_ha, round(r.yield_t_ha / 10, 2), {'index': int(i), 'reference': float(my)}))
        mn = med_n.get(r.crop)
        if mn and r.n_mineral_kg_ha > 0:
            if r.n_mineral_kg_ha > 6 * mn:
                out.append(Finding('farm_survey', key, 'decimal_shift', int(r.year), 'farm.survey',
                                   f'Mineral N {r.n_mineral_kg_ha} kg/ha is {r.n_mineral_kg_ha / mn:.0f}x the {r.crop} median.',
                                   0.8, 'correct', 'n_mineral_kg_ha', r.n_mineral_kg_ha, round(r.n_mineral_kg_ha / 10, 1), {'index': int(i), 'reference': float(mn)}))
            elif r.n_mineral_kg_ha < mn / 6:
                out.append(Finding('farm_survey', key, 'decimal_shift', int(r.year), 'farm.survey',
                                   f'Mineral N {r.n_mineral_kg_ha} kg/ha is far below the {r.crop} median {mn:.0f}.',
                                   0.7, 'correct', 'n_mineral_kg_ha', r.n_mineral_kg_ha, round(r.n_mineral_kg_ha * 10, 1), {'index': int(i), 'reference': float(mn)}))
    return out


@rule('farm.soil')
def farm_soil(raw, checked):
    """The organisers' definition: >= 30 % of the farm's crop area that year on organic soil while the
    survey says mineral. We use the soil map (~88 % accurate), so these go to a human: flagged,
    with the inventory using the map-based organic share."""
    sv, h, p = raw['farm_survey'], raw['crop_history'], raw['parcels']
    hp = h.merge(p[['parcel_id', 'area_ha', 'soil_class_soilmap']], on='parcel_id')
    hp['org'] = hp.area_ha.where(hp.soil_class_soilmap == 'organic', 0.0)
    share = hp.groupby(['farm_id', 'crop', 'year'])[['org', 'area_ha']].sum()
    share = share.org / share.area_ha
    out = []
    for i, r in sv[sv.soil_type_reported == 'Mineral soil'].iterrows():
        s = share.get((r.farm_id, r.crop, r.year))
        if s is not None and s >= 0.30:
            out.append(Finding('farm_survey', f'farm_survey:{r.survey_id}', 'soil_misreport', int(r.year), 'farm.soil',
                               f'Soil map puts {s:.0%} of {r.farm_id}\'s {r.crop} area on organic soil; the survey says mineral.',
                               0.7 if s < 0.5 else 0.85, 'flag', 'soil_type_reported', r.soil_type_reported, f'organic share {s:.2f}',
                               {'index': int(i), 'organic_share': round(float(s), 3)}))
    return out


@rule('farm.coordinates')
def farm_coordinates(raw, checked):
    """Farm centres must lie in the sourcing regions (lat 55–62 °N, lon 12–24 °E); a swapped pair
    lands at lat ~22, lon ~61."""
    fr = raw['farm_registry']
    bad = fr[(fr.lat < 40) & (fr.lon > 40)]
    return [Finding('farm_registry', f'farm:{r.farm_id}', 'coordinate_swap', 2025, 'farm.coordinates',
                    f'lat {r.lat}, lon {r.lon} is outside the sourcing regions; swapped it is ({r.lon}, {r.lat}).',
                    0.95, 'correct', 'lat,lon', [r.lat, r.lon], [r.lon, r.lat], {'index': int(i)}) for i, r in bad.iterrows()]


# ------------------------------------------------------------------ Supplier PCFs and the draft report

@rule('pcf.validity')
def pcf_validity(raw, checked):
    """A PCF is valid for year Y only if its reference period covers Y and its value is per kg
    (METHODOLOGY §4). A value ~1000x the material's library factor, or the same supplier's
    previous-year PCF, is per tonne (or per gram) and is not used."""
    pc = raw['pcfs']
    lib = dict(zip(raw['ef_library'].ef_id, raw['ef_library'].kgco2e_per_unit))
    default = {m: lib.get(ef) for m, ef in zip(raw['materials'].material_id, raw['materials'].default_ef_id)}
    prev = {(r.supplier_id, r.material_id, int(r.year)): r.value for r in pc.itertuples()}
    out = []
    for _, r in pc.iterrows():
        key = f'pcf:{r.supplier_id}:{r.material_id}:{int(r.year)}'
        start, end = pd.Timestamp(r.ref_start), pd.Timestamp(r.ref_end)
        if not (start <= pd.Timestamp(f'{int(r.year)}-01-01') and end >= pd.Timestamp(f'{int(r.year)}-12-31')):
            out.append(Finding('supplier_pcfs', key, 'pcf_stale_period', int(r.year), 'pcf.validity',
                               f'Reference period {r.ref_start}..{r.ref_end} does not cover {int(r.year)}; the library factor is used instead.',
                               0.9, 'drop', locator={'file': r.file}))
        ref = prev.get((r.supplier_id, r.material_id, int(r.year) - 1)) or default.get(r.material_id)
        if r.declared_unit != 'kilogram' or (ref and (r.value > 30 * ref or r.value < ref / 30)):
            out.append(Finding('supplier_pcfs', key, 'pcf_unit_error', int(r.year), 'pcf.validity',
                               f'Declared {r.value} kg CO2e per {r.declared_unit}, vs {ref:.2f} for this supplier last year or the library factor: '
                               f'{r.value / ref:,.0f}x, so not per kg. The library factor is used instead.',
                               0.9, 'drop', locator={'file': r.file}))
    return out


def report_total_check(draft: pd.DataFrame, computed: dict[str, float]) -> list[Finding]:
    """The draft summary is compared with the computed inventory and with its own arithmetic."""
    d = draft.set_index('line').tco2e
    out = []
    parts = d.get('scope1', 0) + d.get('scope2_market', 0) + d.get('scope3', 0)
    if 'total_market_based' in d and abs(parts - d['total_market_based']) > 0.01 * d['total_market_based']:
        out.append(Finding('draft_report_summary', 'report:2025:total_market_based', 'total_mismatch', 2025, 'report.totals',
                           f'Total {d["total_market_based"]:,.0f} ≠ scope 1+2+3 {parts:,.0f}.', 0.95, 'correct', 'tco2e',
                           float(d['total_market_based']), round(sum(computed.get(k, 0) for k in ('scope1_total', 'scope2_market_total', 'scope3_total')), 1)))
    for line, ckey in [('scope1', 'scope1_total'), ('scope2_market', 'scope2_market_total'), ('scope3', 'scope3_total')]:
        if line in d and ckey in computed and computed[ckey] > 0:
            ratio = d[line] / computed[ckey]
            if ratio > 3 or ratio < 1 / 3:
                out.append(Finding('draft_report_summary', f'report:2025:{line}', 'total_mismatch', 2025, 'report.totals',
                                   f'Draft {d[line]:,.0f} is {ratio:,.0f}x the computed {computed[ckey]:,.0f} t.', 0.9, 'correct', 'tco2e',
                                   float(d[line]), round(computed[ckey], 1)))
    return out
