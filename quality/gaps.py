"""The curation method, in one sentence:

    Predict what every number should be, rank the gaps by how many tonnes of CO2 they would
    move, and let a person check the top of the list.

For each number that drives the footprint there is an *expected* value from an independent or
typical source: the shipment record for a purchase, the same month in other years for a meter,
the system's usual top-up for a refrigerant log, and so on (SERIES below).

1. Ratio. r = recorded / expected, looked at on a log scale: g = log10(r). 0 means it matches,
   3 means 1,000x too high.
2. Box plot. Per kind of record, the quartiles Q1, Q3 of g and IQR = Q3 - Q1 give Tukey's fences:
   normal fences at 1.5 IQR beyond the quartiles, far-out fences at 3 IQR.
3. Flag. g is beyond the far-out fences, and the value is at least 2.5x off.
4. Typo test. Typos multiply the true value by a known factor: 1000, 100, 10 (or divide by them),
   or 11.4 for Swedish krona booked as euros. A factor k explains the gap if undoing it puts the
   number back inside the normal fences (widened to at least +-5 %).
5. Decide. Exactly one factor explains the gap -> fixed automatically. Otherwise the best guess
   (the best-fitting factor, else the expected value) goes in, and a person confirms it, picks
   another option, or keeps the original.
6. Tonnes at stake. How much the footprint moves if the fix is applied, with the package's own
   emission factors (quality.impact).
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from types import SimpleNamespace

import numpy as np
import pandas as pd

from quality.impact import Context, farm_impact, impact

FAR_OUT = 3.0           # Tukey's far-out fences: 3 IQR beyond the quartiles -> flagged
NORMAL = 1.5            # Tukey's normal fences: 1.5 IQR -> a typo is undone if it lands back inside
MIN_RATIO = 2.5         # and a flagged number must be at least 2.5x off (tight series have a tiny IQR)
MIN_TOL = 0.02          # 5 %: the normal fences are never narrower than this, even for exact evidence
SEK = 11.4              # FX_PER_EUR['SEK'] in the package; checked at runtime

# (id, factor the typo multiplied the true value by, label shown to the reviewer, kind)
TYPOS = [
    ('div1000', 1000.0, 'Divide by 1,000', 'unit'),
    ('mul1000', 1e-3, 'Multiply by 1,000', 'unit'),
    ('div100', 100.0, 'Divide by 100', 'decimal'),
    ('mul100', 1e-2, 'Multiply by 100', 'decimal'),
    ('div10', 10.0, 'Divide by 10', 'decimal'),
    ('mul10', 0.1, 'Multiply by 10', 'decimal'),
    ('sek', SEK, 'Krona booked as euros: divide by 11.4', 'currency'),
]
T = {t[0]: t for t in TYPOS}
UNIT = [T['div1000'], T['mul1000']]                                  # g/kg, kWh/MWh, l/m3, kg/t
DECIMAL = [T['div10'], T['mul10'], T['div100'], T['mul100']]        # a misplaced decimal point
REPORT_YEARS = (2023, 2024, 2025)

# Raw table name (as in the organisers' record keys) -> key in ccn_tools.io.load_raw()
TABLES = {
    'erp_purchase_lines': 'erp', 'energy_meter_readings': 'energy_meter', 'fuel_deliveries': 'fuel_deliveries',
    'refrigerant_service_log': 'refrigerants', 'waste_transfer_notes': 'waste', 'supplier_pcfs': 'pcfs',
    'farm_survey': 'farm_survey', 'commuting_survey': 'commuting', 'goo_cancellations': 'goo',
}
# When no typo explains a gap, the recorded value stays until a person decides, except for meters:
# a meter cannot jump several-fold for one month, so the same month in other years goes in.
NO_TYPO_DEFAULT = {'energy': 'expected'}


@dataclass
class Item:
    key: str                 # record_key|field: one number in one record
    series: str
    table: str
    record_key: str
    year: int
    field: str
    index: int
    unit: str
    recorded: float | str
    expected: float | str
    expected_from: str       # where the expected value comes from, in words
    context: str             # what the record is (material, site, system…)
    gap: float | None        # log10(recorded / expected)
    fences: dict | None      # the series' box plot: q1, q3, iqr and the fences, in log10 units
    status: str              # fixed | check
    issue_type: str          # the organisers' label, for the error list
    explanation: str
    options: list = field(default_factory=list)   # [{id, label, value, tco2e}]
    default: str = ''        # option applied until a person decides
    tco2e: float = 0.0       # footprint change of the default option
    at_stake: float = 0.0    # the largest |change| among the options: the ranking key
    ai: dict | None = None   # one plain sentence from Claude (quality.ai); explains, never decides

    def row(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------ the series

def _erp(raw):
    e = raw['erp'].copy()
    e['year'] = e.posting_date.str[:4].astype(int)
    e['key'] = 'erp:' + e.doc_no.astype(str) + ':' + e.line_no.astype(str)
    e['k'] = np.where(e.uom == 'TO', 1000.0, 1.0)  # kg per line unit
    return e


def _fx(raw):
    from ccn_tools import factors as F
    return F.FX_PER_EUR


def s_purchases(raw):
    """Goods receipts vs the tonnes the inbound shipments carried for the same document."""
    e = _erp(raw)
    legs = raw['shipments'][raw['shipments'].direction == 'inbound']
    t = legs.groupby(legs.ref_doc.astype(str)).t.median()
    g = e[e.uom.isin(['KG', 'TO']) & (e.movement_type == 101) & (e.quantity > 0)].copy()
    g['ship_kg'] = g.doc_no.astype(str).map(t) * 1000
    g = g[g.ship_kg > 0]
    return pd.DataFrame({'index': g.index, 'record_key': g.key, 'year': g.year, 'recorded': g.quantity,
                         'expected': g.ship_kg / g.k, 'unit': g.uom.str.lower(), 'context': g.material_text})


def s_purchases_price(raw):
    """Goods receipts with no shipment record: quantity vs amount paid / the material's typical price."""
    e = _erp(raw)
    fx = _fx(raw)
    e['eur'] = e.net_amount / e.currency.map(fx).fillna(1.0)
    goods = e[e.uom.isin(['KG', 'TO']) & (e.movement_type == 101) & (e.quantity > 0) & (e.eur > 0)].copy()
    price = (goods.eur / (goods.quantity * goods.k)).groupby(goods.material_id).median()
    legs = raw['shipments'][raw['shipments'].direction == 'inbound']
    g = goods[~goods.doc_no.astype(str).isin(set(legs.ref_doc.astype(str)))]
    return pd.DataFrame({'index': g.index, 'record_key': g.key, 'year': g.year, 'recorded': g.quantity,
                         'expected': g.eur / g.material_id.map(price) / g.k, 'unit': g.uom.str.lower(), 'context': g.material_text})


def s_goods_amount(raw):
    """Amount paid for goods vs kilos x the material's typical price per kg. The kilos come from the
    shipment record where there is one, so a price that is off points at the amount, not the kilos."""
    e = _erp(raw)
    fx = _fx(raw)
    legs = raw['shipments'][raw['shipments'].direction == 'inbound']
    t = legs.groupby(legs.ref_doc.astype(str)).t.median()
    g = e[e.uom.isin(['KG', 'TO']) & (e.movement_type == 101) & (e.quantity > 0) & (e.net_amount > 0)].copy()
    g['kg'] = (g.doc_no.astype(str).map(t) * 1000).fillna(g.quantity * g.k)
    g['rate'] = g.currency.map(fx).fillna(1.0)
    price = (g.net_amount / g.rate / g.kg).groupby(g.material_id).median()
    return pd.DataFrame({'index': g.index, 'record_key': g.key, 'year': g.year, 'recorded': g.net_amount,
                         'expected': g.kg * g.material_id.map(price) * g.rate, 'unit': g.currency, 'context': g.material_text})


def s_spend(raw):
    """Spend-based lines (services, capex) vs the supplier's typical invoice. Amounts are compared in
    euros, so a supplier that bills in more than one currency is not mistaken for a typo; the
    prediction is then converted back into the line's own currency."""
    e = _erp(raw)
    g = e[(e.uom == 'EUR') & (e.movement_type == 101) & (e.net_amount > 0)].copy()
    g['rate'] = g.currency.map(_fx(raw)).fillna(1.0)
    g['eur'] = g.net_amount / g.rate
    n = g.groupby('supplier_id').eur.transform('size')
    g = g[n >= 5]
    med_eur = g.groupby('supplier_id').eur.transform('median')
    return pd.DataFrame({'index': g.index, 'record_key': g.key, 'year': g.year, 'recorded': g.net_amount,
                         'expected': med_eur * g.rate, 'unit': g.currency, 'context': g.material_text})


def s_energy(raw):
    """Monthly meter readings vs the same month in the other years (median of all years)."""
    m = raw['energy_meter'].copy()
    med = m.groupby(['site_id', 'carrier', 'month']).value.transform('median')
    n = m.groupby(['site_id', 'carrier', 'month']).value.transform('size')
    m = m[(n >= 3) & (med > 0)]
    med = med[m.index]
    key = 'energy:' + m.site_id + ':' + m.year.astype(str) + '-' + m.month.map('{:02d}'.format) + ':' + m.carrier
    return pd.DataFrame({'index': m.index, 'record_key': key, 'year': m.year, 'recorded': m.value,
                         'expected': med, 'unit': m.unit, 'context': m.site_id + ' ' + m.carrier})


def _by_group_median(df, value, by, min_n=3):
    med = df.groupby(by)[value].transform('median')
    n = df.groupby(by)[value].transform('size')
    keep = (n >= min_n) & (med > 0) & (df[value] > 0)
    return df[keep], med[keep]


def s_refrigerants(raw):
    """Top-ups vs the same system's usual top-up."""
    r, med = _by_group_median(raw['refrigerants'], 'kg_added', ['site_id', 'system'])
    return pd.DataFrame({'index': r.index, 'record_key': 'refrigerant:' + r.event_id, 'year': r.year, 'recorded': r.kg_added,
                         'expected': med, 'unit': 'kg', 'context': r.site_id + ' ' + r.system + ' (' + r.refrigerant + ')'})


def s_fuel(raw):
    """Fuel deliveries vs the carrier's usual delivery."""
    f, med = _by_group_median(raw['fuel_deliveries'], 'quantity', ['carrier', 'unit'])
    return pd.DataFrame({'index': f.index, 'record_key': 'fuel:' + f.delivery_id.astype(str), 'year': f.year, 'recorded': f.quantity,
                         'expected': med, 'unit': f.unit, 'context': f.site_id + ' ' + f.carrier})


def s_waste(raw):
    """Waste notes vs the stream's usual note at that site."""
    w, med = _by_group_median(raw['waste'], 'quantity', ['site_id', 'waste_stream'])
    return pd.DataFrame({'index': w.index, 'record_key': 'waste:' + w.transfer_note.astype(str), 'year': w.year, 'recorded': w.quantity,
                         'expected': med, 'unit': w.unit, 'context': w.site_id + ' ' + w.waste_stream})


def s_pcf(raw):
    """Supplier footprints (kg CO2e per kg) vs the same supplier's previous year, else the library factor."""
    pc = raw['pcfs']
    lib = dict(zip(raw['ef_library'].ef_id, raw['ef_library'].kgco2e_per_unit))
    default = {m: lib.get(ef) for m, ef in zip(raw['materials'].material_id, raw['materials'].default_ef_id)}
    prev = {(r.supplier_id, r.material_id, int(r.year)): r.value for r in pc.itertuples()}
    exp = [prev.get((r.supplier_id, r.material_id, int(r.year) - 1)) or default.get(r.material_id) for r in pc.itertuples()]
    d = pd.DataFrame({'index': pc.index, 'record_key': 'pcf:' + pc.supplier_id + ':' + pc.material_id + ':' + pc.year.astype(str),
                      'year': pc.year, 'recorded': pc.value, 'expected': exp, 'unit': 'kg CO2e/kg', 'context': pc.supplier_id + ' ' + pc.material_id})
    return d[d.expected.notna() & (d.expected > 0)]


def s_commuting(raw):
    """One-way commuting distances vs the site's typical distance (the survey is from 2025)."""
    c, med = _by_group_median(raw['commuting'], 'one_way_km', ['site_id'])
    return pd.DataFrame({'index': c.index, 'record_key': 'commute:' + c.response_id.astype(str), 'year': 2025, 'recorded': c.one_way_km,
                         'expected': med, 'unit': 'km', 'context': c.site_id + ' ' + c['mode'].astype(str)})


def s_farm(raw, col, label):
    sv = raw['farm_survey']
    s, med = _by_group_median(sv, col, ['crop', 'year'], min_n=5)
    return pd.DataFrame({'index': s.index, 'record_key': 'farm_survey:' + s.survey_id, 'year': s.year, 'recorded': s[col],
                         'expected': med, 'unit': label, 'context': s.farm_id + ' ' + s.crop})


# name -> (label, table, field, builder, expected_from, typos)
SERIES = {
    # Each kind of record has its own realistic typos.
    'purchases': ('Purchases', 'erp_purchase_lines', 'quantity', s_purchases, 'the tonnes the shipment carried for this purchase', UNIT + DECIMAL),
    'purchases_price': ('Purchases without a shipment record', 'erp_purchase_lines', 'quantity', s_purchases_price, 'the amount paid ÷ the material\'s typical price', UNIT + DECIMAL),
    'goods_amount': ('Amounts paid for goods', 'erp_purchase_lines', 'net_amount', s_goods_amount, 'the kilos × the material\'s typical price', [T['sek']]),
    'spend': ('Services and capex', 'erp_purchase_lines', 'net_amount', s_spend, 'the supplier\'s typical invoice', [T['sek']]),
    'energy': ('Energy meters', 'energy_meter_readings', 'value', s_energy, 'the same month in the other years', UNIT),
    'refrigerants': ('Refrigerant top-ups', 'refrigerant_service_log', 'kg_added', s_refrigerants, 'the system\'s usual top-up', UNIT),
    'fuel': ('Fuel deliveries', 'fuel_deliveries', 'quantity', s_fuel, 'the carrier\'s usual delivery', UNIT),
    'waste': ('Waste notes', 'waste_transfer_notes', 'quantity', s_waste, 'the stream\'s usual note at this site', UNIT),
    'pcf': ('Supplier footprints', 'supplier_pcfs', 'value', s_pcf, 'the supplier\'s previous year, else the library factor', UNIT),
    'commuting': ('Commuting distances', 'commuting_survey', 'one_way_km', s_commuting, 'the site\'s typical one-way distance', UNIT),
    'farm_yield': ('Farm yields', 'farm_survey', 'yield_t_ha', lambda raw: s_farm(raw, 'yield_t_ha', 't/ha'), 'the crop\'s median yield that year', DECIMAL),
    'farm_n': ('Farm fertiliser (mineral N)', 'farm_survey', 'n_mineral_kg_ha', lambda raw: s_farm(raw, 'n_mineral_kg_ha', 'kg N/ha'), 'the crop\'s median that year', DECIMAL),
}


# ------------------------------------------------------------------ the method

def box(gaps: np.ndarray) -> dict:
    """Tukey's box plot of the log ratios: quartiles, IQR, normal (1.5 IQR) and far-out (3 IQR) fences."""
    q1, q3 = (float(x) for x in np.percentile(gaps, [25, 75])) if len(gaps) else (0.0, 0.0)
    iqr = q3 - q1
    return {'q1': q1, 'q3': q3, 'iqr': iqr,
            'normal': (min(q1 - NORMAL * iqr, -MIN_TOL), max(q3 + NORMAL * iqr, MIN_TOL)),
            'farOut': (q1 - FAR_OUT * iqr, q3 + FAR_OUT * iqr)}


def flagged(g: float, b: dict) -> bool:
    """Beyond the far-out fences and at least 2.5x off."""
    lo, hi = b['farOut']
    return (g < lo or g > hi) and abs(g) >= math.log10(MIN_RATIO)


def fitting_typos(g: float, b: dict, typos=TYPOS) -> list[tuple]:
    """Typos that explain a gap g: undoing them puts the number back inside the normal fences. Best first."""
    lo, hi = b['normal']
    fits = [(abs(g - math.log10(t[1])), t) for t in typos if lo <= g - math.log10(t[1]) <= hi]
    return [t for _, t in sorted(fits, key=lambda x: x[0])]


def issue_type(series: str, typo) -> str:
    if typo is None:
        return 'meter_spike' if series == 'energy' else 'outlier_implausible'
    kind = typo[3]
    if kind == 'currency':
        return 'currency_error'
    if series == 'pcf':
        return 'pcf_unit_error'
    if series == 'farm_yield':
        return 'outlier_implausible'
    return 'unit_error' if kind == 'unit' else 'decimal_shift'


class Impact:
    """Tonnes of CO2e a change would move, with the package's factors (quality.impact)."""

    def __init__(self, raw):
        self.ctx = Context(raw)
        self.raw = raw
        e = _erp(raw)
        e['kg'] = e.quantity * e.k
        self.kg = e.groupby(['supplier_id', 'material_id', 'year']).kg.sum()

    def __call__(self, it: Item, new) -> float:
        if new is None or new == it.recorded:
            return 0.0
        if it.series == 'missing':
            it = Item(**{**it.row(), 'recorded': 0.0})
        if it.series == 'commuting':
            c = self.raw['commuting']
            r = c.loc[it.index]
            hc = self.raw['headcount']
            hc = float(hc[(hc.year == 2025) & (hc.site_id == r.site_id)].headcount.sum())
            lib = self.ctx.lib
            ef = {'car': lib['EF-PKM-CAR'], 'carpool': lib['EF-PKM-CAR'] / 2, 'bus': lib['EF-PKM-BUS'], 'train': lib['EF-PKM-TRAIN'],
                  'bike_walk': 0.0, 'ev_car': 0.03}.get(r['mode'], lib['EF-PKM-CAR'])
            n = int((c.site_id == r.site_id).sum())
            return round((float(new) - float(it.recorded)) * 2 * r.days_on_site_per_week * 46 * ef * hc / n / 1000, 3)
        if it.series == 'pcf':
            sup, mat, year = it.record_key.split(':')[1:4]
            return float(self.kg.get((sup, mat, int(year)), 0.0)) * (float(new) - float(it.recorded)) / 1000
        f = SimpleNamespace(table=it.table, record_key=it.record_key, field=it.field, observed=it.recorded, proposed=new,
                            action='correct', locator={'index': it.index, 'organic_share': new if it.field == 'soil' else None},
                            year=it.year, issue_type=it.issue_type)
        try:
            _, d = farm_impact(f, self.ctx) if it.table == 'farm_survey' else impact(f, self.ctx)
        except Exception:  # an estimate must never break the run
            return 0.0
        return 0.0 if d is None or (isinstance(d, float) and math.isnan(d)) else round(float(d), 3)


def evaluate(raw, imp: Impact | None = None):
    """Run every series. Returns (items, points, series_meta)."""
    global SEK
    SEK = float(_fx(raw).get('SEK', SEK))
    imp = imp or Impact(raw)
    items, points, meta = [], [], {}
    rng = np.random.default_rng(0)
    for name, (label, table, fld, build, expected_from, typos) in SERIES.items():
        d = build(raw)
        d = d[(d.recorded > 0) & (d.expected > 0)].copy()
        if d.empty:
            continue
        d['gap'] = np.log10(d.recorded.astype(float).values / d.expected.astype(float).values)
        b = box(d.gap.values)
        d['flag'] = [flagged(g, b) and y in REPORT_YEARS for g, y in zip(d.gap, d.year)]
        fences = {'q1': round(b['q1'], 4), 'q3': round(b['q3'], 4), 'iqr': round(b['iqr'], 4),
                  'normal': [round(x, 4) for x in b['normal']], 'farOut': [round(x, 4) for x in b['farOut']]}
        meta[name] = {'label': label, 'expectedFrom': expected_from, 'box': fences, 'n': int(len(d)), 'flagged': int(d.flag.sum())}
        for r in d[d.flag].itertuples():
            fits = fitting_typos(r.gap, b, typos)
            best = fits[0] if fits else None
            exp = float(r.expected)
            options = [{'id': t[0], 'label': t[2], 'value': round(float(r.recorded) / t[1], 6)} for t in fits]
            options.append({'id': 'expected', 'label': f'Use the expected value ({_fmt(exp)} {r.unit})', 'value': round(exp, 6)})
            options.append({'id': 'keep', 'label': 'Keep the recorded value', 'value': float(r.recorded)})
            ratio = 10 ** r.gap
            why = (f'Recorded {_fmt(r.recorded)} {r.unit}; expected about {_fmt(exp)} from {expected_from} '
                   f'({_fmt(ratio) + "x" if ratio >= 1 else "1/" + _fmt(1 / ratio)} off). ')
            if len(fits) == 1:
                why += f'Only one typo explains it: {best[2].lower()}.'
            elif fits:
                why += f'Several typos fit ({", ".join(t[2].lower() for t in fits)}): you choose.'
            else:
                why += 'No typo explains it: check whether it is real.'
            it = Item(key=f'{r.record_key}|{fld}', series=name, table=table, record_key=r.record_key, year=int(r.year), field=fld,
                      index=int(r.index), unit=str(r.unit), recorded=float(r.recorded), expected=round(exp, 6), expected_from=expected_from,
                      context=str(r.context), gap=round(float(r.gap), 4), fences=fences, status='fixed' if len(fits) == 1 else 'check',
                      issue_type=issue_type(name, best), explanation=why, options=options,
                      default=best[0] if best else NO_TYPO_DEFAULT.get(name, 'keep'))
            for o in options:
                o['tco2e'] = imp(it, o['value'])
            it.tco2e = next(o['tco2e'] for o in options if o['id'] == it.default)
            it.at_stake = round(max(abs(o['tco2e']) for o in options), 3)
            items.append(it)
        # scatter: every flagged point and a sample of the normal ones
        normal = d[~d.flag]
        if len(normal) > 400:
            normal = normal.iloc[np.sort(rng.choice(len(normal), 400, replace=False))]
        st = {it.record_key: it.status for it in items if it.series == name}
        for r in pd.concat([normal, d[d.flag]]).itertuples():
            points.append({'s': name, 'x': round(math.log10(float(r.expected)), 3), 'y': round(math.log10(float(r.recorded)), 3),
                           'st': st.get(r.record_key, 'ok'), 'k': r.record_key})
    for name, label, fn in (('missing', 'Missing meter months', missing_months), ('gas', 'Refrigerant gas code', gas),
                            ('goo', 'Green-electricity certificates', goo)):
        new = fn(raw, imp)
        items += new
        meta[name] = {'label': label, 'expectedFrom': new[0].expected_from if new else '', 'flagged': len(new)}
    items += soil(raw, imp)
    meta['soil'] = {'label': 'Soil type (farm survey vs soil map)', 'expectedFrom': 'the soil map', 'n': int((raw['farm_survey'].soil_type_reported == 'Mineral soil').sum()),
                    'flagged': sum(1 for i in items if i.series == 'soil')}
    return items, points, meta


def organic_share(raw) -> pd.Series:
    """Share of each farm's crop area on organic (peat) soil per year, from the soil map."""
    hp = raw['crop_history'].merge(raw['parcels'][['parcel_id', 'area_ha', 'soil_class_soilmap']], on='parcel_id')
    hp['org'] = hp.area_ha.where(hp.soil_class_soilmap == 'organic', 0.0)
    s = hp.groupby(['farm_id', 'crop', 'year'])[['org', 'area_ha']].sum()
    return s.org / s.area_ha


def _categorical(imp, *, key, series, table, record_key, year, field, index, recorded, expected, expected_from, context,
                 issue, why, use_label, keep_label, unit=''):
    it = Item(key=key, series=series, table=table, record_key=record_key, year=year, field=field, index=index, unit=unit,
              recorded=recorded, expected=expected, expected_from=expected_from, context=context, gap=None, fences=None,
              status='check', issue_type=issue, explanation=why, default='use',
              options=[{'id': 'use', 'label': use_label, 'value': expected}, {'id': 'keep', 'label': keep_label, 'value': recorded}])
    for o in it.options:
        o['tco2e'] = imp(it, o['value'])
    it.tco2e = it.options[0]['tco2e']
    it.at_stake = abs(it.tco2e)
    return it


def missing_months(raw, imp: Impact) -> list[Item]:
    """A month missing from a meter that reported most of the year: the expected value (the same month
    in the other years) goes in until a person decides."""
    m = raw['energy_meter']
    med = m.groupby(['site_id', 'carrier', 'month']).value.median()
    out = []
    for (site, carrier, year), g in m[m.year.isin(REPORT_YEARS)].groupby(['site_id', 'carrier', 'year']):
        if len(g) < 8:
            continue
        for month in sorted(set(range(1, 13)) - set(g.month)):
            exp = med.get((site, carrier, month))
            if exp is None or exp <= 0:
                continue
            rk = f'energy:{site}:{int(year)}-{month:02d}:{carrier}'
            it = _categorical(imp, key=f'{rk}|missing', series='missing', table='energy_meter_readings', record_key=rk, year=int(year),
                              field='missing', index=-1, recorded='missing', expected=round(float(exp), 3), unit='MWh',
                              expected_from='the same month in the other years', context=f'{site} {carrier}', issue='missing_record',
                              why=f'No reading for {year}-{month:02d}; the same month in the other years was about {exp:,.0f} MWh.',
                              use_label=f'Add the expected {exp:,.0f} MWh', keep_label='Leave the month empty')
            it.options[1]['value'] = None
            it.options[1]['tco2e'] = 0.0
            out.append(it)
    return out


def gas(raw, imp: Impact) -> list[Item]:
    """A gas code that differs from the gas the system uses in most (>= 60 %, >= 3) of its events."""
    out = []
    r = raw['refrigerants']
    for (site, system), g in r.groupby(['site_id', 'system']):
        counts = g.refrigerant.value_counts()
        usual = counts.index[0]
        if counts.iloc[0] < 3 or counts.iloc[0] / counts.sum() < 0.6:
            continue
        for i, x in g[(g.refrigerant != usual) & g.year.isin(REPORT_YEARS)].iterrows():
            out.append(_categorical(imp, key=f'refrigerant:{x.event_id}|refrigerant', series='gas', table='refrigerant_service_log',
                                    record_key=f'refrigerant:{x.event_id}', year=int(x.year), field='refrigerant', index=int(i),
                                    recorded=x.refrigerant, expected=usual, expected_from='the gas this system uses', context=f'{site} {system}',
                                    issue='wrong_gas_code', why=f'{system} uses {usual} in {counts.iloc[0]} of {counts.sum()} services; this one says {x.refrigerant}.',
                                    use_label=f'Use {usual}', keep_label=f'Keep {x.refrigerant}'))
    return out


def goo(raw, imp: Impact) -> list[Item]:
    """The internal certificate log vs the national registry statement: vintage and MWh."""
    g = raw['goo']
    reg = pd.read_csv(raw['_package'] / 'data/02_raw_feeds/goo_registry_statement.csv') if '_package' in raw else raw.get('goo_registry')
    if reg is None:
        return []
    tot = reg.groupby(['consumption_year', 'beneficiary_site']).mwh.sum()
    out = []
    for i, r in g.iterrows():
        k = (int(r.year), r.site_id)
        if k not in tot.index or int(r.year) not in REPORT_YEARS:
            continue
        rk = f'goo:{r.site_id}:{int(r.year)}'
        if int(r.vintage_year) != int(r.year):
            out.append(_categorical(imp, key=f'{rk}|vintage_year', series='goo', table='goo_cancellations', record_key=rk, year=int(r.year),
                                    field='vintage_year', index=int(i), recorded=int(r.vintage_year), expected=int(r.year),
                                    expected_from='the national registry', context=f'{r.site_id} certificates',
                                    issue='certificate_mismatch', why=f'The log says the certificates were produced in {int(r.vintage_year)}; the registry says {int(r.year)}, the year they are used for.',
                                    use_label=f'Use the registry ({int(r.year)})', keep_label=f'Keep {int(r.vintage_year)}'))
        mwh = float(tot[k])
        if abs(r.mwh_cancelled - mwh) > max(1.0, 0.01 * mwh):
            out.append(_categorical(imp, key=f'{rk}|mwh_cancelled', series='goo', table='goo_cancellations', record_key=rk, year=int(r.year),
                                    field='mwh_cancelled', index=int(i), recorded=float(r.mwh_cancelled), expected=round(mwh, 3), unit='MWh',
                                    expected_from='the national registry', context=f'{r.site_id} certificates',
                                    issue='certificate_mismatch', why=f'The log says {r.mwh_cancelled:,.0f} MWh; the registry shows {mwh:,.0f} MWh.',
                                    use_label=f'Use the registry ({mwh:,.0f} MWh)', keep_label=f'Keep {r.mwh_cancelled:,.0f} MWh'))
    return out


def soil(raw, imp: Impact) -> list[Item]:
    """The one non-numeric check: the farmer ticked mineral soil, the soil map puts >= 30 % of that
    crop's area on peat (the organisers' definition of a misreport). The map is ~88 % accurate, so
    a person always decides; until then the footprint uses the map."""
    share = organic_share(raw)
    out = []
    sv = raw['farm_survey']
    for i, r in sv[(sv.soil_type_reported == 'Mineral soil') & sv.year.isin(REPORT_YEARS)].iterrows():
        s = share.get((r.farm_id, r.crop, r.year))
        if s is None or s < 0.30:
            continue
        it = Item(key=f'farm_survey:{r.survey_id}|soil', series='soil', table='farm_survey', record_key=f'farm_survey:{r.survey_id}',
                  year=int(r.year), field='soil', index=int(i), unit='peat share', recorded='Mineral soil', expected=round(float(s), 3),
                  expected_from='the soil map', context=f'{r.farm_id} {r.crop}', gap=None, fences=None, status='check',
                  issue_type='soil_misreport', default='map',
                  explanation=f'The farmer ticked mineral soil; the soil map puts {s:.0%} of this {r.crop} area on peat. The map is right about 88 % of the time.',
                  options=[{'id': 'map', 'label': f'Use the soil map ({s:.0%} peat)', 'value': round(float(s), 3)},
                           {'id': 'keep', 'label': 'Keep the farmer\'s answer (mineral)', 'value': 0.0}])
        it.options[0]['tco2e'] = imp(it, float(s))
        it.options[1]['tco2e'] = 0.0
        it.tco2e = it.options[0]['tco2e']
        it.at_stake = abs(it.tco2e)
        out.append(it)
    return out


def _fmt(x) -> str:
    x = float(x)
    if x == 0:
        return '0'
    if abs(x) >= 100:
        return f'{x:,.0f}'
    if abs(x) >= 1:
        return f'{x:,.2f}'.rstrip('0').rstrip('.')
    return f'{x:.3g}'


def choice(it: Item, decisions: dict) -> str:
    """The option in force: a person's decision if there is one, else the default."""
    d = decisions.get(it.key)
    return d if d and any(o['id'] == d for o in it.options) else it.default


def apply(raw, items, decisions: dict):
    """A corrected copy of the raw tables (raw stays untouched), plus the surveys where the farmer's
    soil answer is kept instead of the soil map."""
    out = {k: (v.copy() if isinstance(v, pd.DataFrame) else v) for k, v in raw.items()}
    keep_soil = set()
    for it in items:
        c = choice(it, decisions)
        if c == 'keep':
            if it.series == 'soil':
                keep_soil.add(it.record_key.split(':', 1)[1])
            continue
        if it.series == 'soil':
            continue
        value = next(o['value'] for o in it.options if o['id'] == c)
        if it.series == 'missing':
            _, site, ym, carrier = it.record_key.split(':')
            row = {'site_id': site, 'year': int(ym[:4]), 'month': int(ym[5:]), 'carrier': carrier, 'value': value, 'unit': 'MWh'}
            out['energy_meter'] = pd.concat([out['energy_meter'], pd.DataFrame([row])], ignore_index=True)
            continue
        out[TABLES[it.table]].loc[it.index, it.field] = value
    return out, keep_soil
